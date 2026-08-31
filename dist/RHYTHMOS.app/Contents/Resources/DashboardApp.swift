import Cocoa
import WebKit

final class DashboardWindow: NSWindow {
    override func keyDown(with event: NSEvent) {
        let commandPressed = event.modifierFlags.contains(.command)
        let key = event.charactersIgnoringModifiers?.lowercased()
        if commandPressed && key == "q" {
            NSApp.terminate(nil)
            return
        }
        if commandPressed && key == "w" {
            performClose(nil)
            return
        }
        if commandPressed && key == "m" {
            miniaturize(nil)
            return
        }
        super.keyDown(with: event)
    }
}

final class DashboardAppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var keyEventMonitor: Any?
    private var revealWhenDashboardLoads = false

    private static let downloadBridgeScript = #"""
    document.addEventListener("click", function(event) {
      const element = event.target instanceof Element ? event.target : null;
      const anchor = element ? element.closest("a[download]") : null;
      if (!anchor || anchor.dataset.rhythmosDownloading === "1") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      anchor.dataset.rhythmosDownloading = "1";
      fetch(anchor.href)
        .then(function(response) {
          if (!response.ok) throw new Error("DOWNLOAD_HTTP_" + response.status);
          return response.blob();
        })
        .then(function(blob) {
          return new Promise(function(resolve, reject) {
            const reader = new FileReader();
            reader.onload = function() { resolve(reader.result); };
            reader.onerror = function() { reject(reader.error); };
            reader.readAsDataURL(blob);
          });
        })
        .then(function(dataURL) {
          const comma = String(dataURL).indexOf(",");
          if (comma < 0) throw new Error("DOWNLOAD_DATA_INVALID");
          window.webkit.messageHandlers.rhythmosDownload.postMessage({
            filename: anchor.download || "rhythmos_export.csv",
            base64: String(dataURL).slice(comma + 1)
          });
        })
        .catch(function(error) {
          window.webkit.messageHandlers.rhythmosDownload.postMessage({
            error: String(error && error.message ? error.message : error)
          });
        })
        .finally(function() {
          delete anchor.dataset.rhythmosDownloading;
        });
    }, true);
    """#

    func applicationDidFinishLaunching(_ notification: Notification) {
        installApplicationMenu()
        installQuitShortcut()
        let frame = NSRect(x: 0, y: 0, width: 1280, height: 820)
        window = DashboardWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "RHYTHMOS｜律衡"
        window.center()
        window.setFrameAutosaveName("DailyRecoveryCoachWindow")

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(self, name: "rhythmosDownload")
        configuration.userContentController.addUserScript(WKUserScript(
            source: Self.downloadBridgeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        webView = WKWebView(frame: frame, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window.contentView = webView
        startDashboard()
    }

    func webView(
        _ webView: WKWebView,
        runOpenPanelWith parameters: WKOpenPanelParameters,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping ([URL]?) -> Void
    ) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.resolvesAliases = true
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard revealWhenDashboardLoads else { return }
        revealWhenDashboardLoads = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        preferences: WKWebpagePreferences,
        decisionHandler: @escaping (WKNavigationActionPolicy, WKWebpagePreferences) -> Void
    ) {
        decisionHandler(navigationAction.shouldPerformDownload ? .download : .allow, preferences)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        let response = navigationResponse.response
        let contentDisposition = (response as? HTTPURLResponse)?
            .value(forHTTPHeaderField: "Content-Disposition")?.lowercased() ?? ""
        let isAttachment = contentDisposition.contains("attachment")
        let isCSV = response.mimeType?.lowercased() == "text/csv"
        decisionHandler(
            isAttachment || isCSV || !navigationResponse.canShowMIMEType ? .download : .allow
        )
    }

    func webView(
        _ webView: WKWebView,
        navigationAction: WKNavigationAction,
        didBecome download: WKDownload
    ) {
        download.delegate = self
    }

    func webView(
        _ webView: WKWebView,
        navigationResponse: WKNavigationResponse,
        didBecome download: WKDownload
    ) {
        download.delegate = self
    }

    func download(
        _ download: WKDownload,
        decideDestinationUsing response: URLResponse,
        suggestedFilename: String,
        completionHandler: @escaping (URL?) -> Void
    ) {
        chooseExportDestination(for: suggestedFilename, completion: completionHandler)
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "rhythmosDownload",
              let body = message.body as? [String: Any] else { return }
        if let error = body["error"] as? String {
            showDownloadResult(destination: nil, error: error)
            return
        }
        guard let base64 = body["base64"] as? String,
              let data = Data(base64Encoded: base64) else {
            showDownloadResult(destination: nil, error: "DOWNLOAD_DATA_INVALID")
            return
        }
        chooseExportDestination(for: body["filename"] as? String ?? "rhythmos_export.csv") { destination in
            guard let destination else { return }
            do {
                try data.write(to: destination, options: .atomic)
                self.showDownloadResult(destination: destination, error: nil)
            } catch {
                self.showDownloadResult(destination: nil, error: error.localizedDescription)
            }
        }
    }

    private func chooseExportDestination(
        for suggestedFilename: String,
        completion: @escaping (URL?) -> Void
    ) {
        let rawFilename = URL(fileURLWithPath: suggestedFilename).lastPathComponent
        let filename = rawFilename.isEmpty ? "rhythmos_export.csv" : rawFilename
        DispatchQueue.main.async {
            let panel = NSSavePanel()
            panel.title = "导出 CSV"
            panel.message = "选择 CSV 文件保存位置"
            panel.nameFieldStringValue = filename
            panel.canCreateDirectories = true
            panel.allowedFileTypes = ["csv"]
            panel.directoryURL = FileManager.default.urls(
                for: .downloadsDirectory,
                in: .userDomainMask
            ).first
            panel.beginSheetModal(for: self.window) { response in
                completion(response == .OK ? panel.url : nil)
            }
        }
    }

    private func showDownloadResult(destination: URL?, error: String?) {
        DispatchQueue.main.async {
            let alert = NSAlert()
            if let destination {
                alert.alertStyle = .informational
                alert.messageText = "CSV 已导出"
                alert.informativeText = destination.path
                alert.addButton(withTitle: "完成")
                alert.addButton(withTitle: "在 Finder 中显示")
                let response = alert.runModal()
                if response == .alertSecondButtonReturn {
                    NSWorkspace.shared.activateFileViewerSelecting([destination])
                }
            } else {
                alert.alertStyle = .warning
                alert.messageText = "CSV 导出失败"
                alert.informativeText = error ?? "DOWNLOAD_FAILED"
                alert.addButton(withTitle: "关闭")
                alert.runModal()
            }
        }
    }

    private func installQuitShortcut() {
        keyEventMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let key = event.charactersIgnoringModifiers?.lowercased()
            if modifiers == [.command] && key == "q" {
                NSApp.terminate(nil)
                return nil
            }
            if modifiers == [.command] && key == "w" {
                self.window.performClose(nil)
                return nil
            }
            if modifiers == [.command] && key == "m" {
                self.window.miniaturize(nil)
                return nil
            }
            if modifiers == [.command, .control] && key == "f" {
                self.window.toggleFullScreen(nil)
                return nil
            }
            return event
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let monitor = keyEventMonitor {
            NSEvent.removeMonitor(monitor)
            keyEventMonitor = nil
        }
    }

    private func installApplicationMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem(title: "RHYTHMOS｜律衡", action: nil, keyEquivalent: "")
        let appMenu = NSMenu()
        let quitItem = NSMenuItem(
            title: "退出 RHYTHMOS｜律衡",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        quitItem.keyEquivalentModifierMask = [.command]
        appMenu.addItem(quitItem)
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        // Keep the standard responder-chain editing actions available to the
        // WKWebView. Without an Edit menu, Command-C/Command-V can be ignored
        // by the native shell even though the web page itself supports them.
        let editMenuItem = NSMenuItem(title: "编辑", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "编辑")
        let editActions: [(String, Selector, String)] = [
            ("剪切", #selector(NSText.cut(_:)), "x"),
            ("复制", #selector(NSText.copy(_:)), "c"),
            ("粘贴", #selector(NSText.paste(_:)), "v"),
            ("全选", #selector(NSText.selectAll(_:)), "a"),
        ]
        for (title, action, keyEquivalent) in editActions {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
            item.keyEquivalentModifierMask = [.command]
            editMenu.addItem(item)
        }
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)
        NSApp.mainMenu = mainMenu
    }

    func applicationShouldTerminateAfterLastWindowClosed(
        _ sender: NSApplication
    ) -> Bool {
        return true
    }

    private func startDashboard() {
        DispatchQueue.global(qos: .userInitiated).async {
            let fileManager = FileManager.default
            let uid = getuid()
            let urlPath = "/tmp/daily-recovery-coach-url-\(uid).txt"
            let errorPath = "/tmp/daily-recovery-coach-error-\(uid).txt"
            try? fileManager.removeItem(atPath: urlPath)
            try? fileManager.removeItem(atPath: errorPath)
            // Prefer the project directory next to this App bundle so the
            // application keeps working when the project folder is renamed
            // or moved. The build-time path remains a fallback for a copied
            // App bundle that is launched outside the project tree.
            let bundledProjectRoot = Bundle.main.bundleURL
                .deletingLastPathComponent()
                .deletingLastPathComponent()
            let embeddedProjectRoot = URL(fileURLWithPath: "/Users/liuxi/Documents/RHYTHMOS")
            let projectRootURL = [bundledProjectRoot, embeddedProjectRoot].first {
                fileManager.fileExists(atPath: $0.appendingPathComponent(".venv/bin/python").path)
                    && fileManager.fileExists(atPath: $0.appendingPathComponent("src/dashboard_launcher.py").path)
            }
            guard let projectRootURL else {
                self.showLaunchError(message: "DASHBOARD_PROJECT_ROOT_NOT_FOUND")
                return
            }
            self.startStartupCatchUp(projectRootURL)
            guard fileManager.createFile(atPath: urlPath, contents: nil),
                  fileManager.createFile(atPath: errorPath, contents: nil),
                  let standardOutput = FileHandle(forWritingAtPath: urlPath),
                  let standardError = FileHandle(forWritingAtPath: errorPath) else {
                self.showLaunchError(message: "DASHBOARD_LOG_FILE_CREATE_FAILED")
                return
            }
            defer {
                try? standardOutput.close()
                try? standardError.close()
            }

            let pythonURL = projectRootURL.appendingPathComponent(".venv/bin/python")
            let launcherURL = projectRootURL.appendingPathComponent("src/dashboard_launcher.py")
            let process = Process()
            // Start the local launcher directly. A dashboard launch must never
            // open Terminal or expose a temporary shell script to the user.
            process.executableURL = pythonURL
            process.arguments = [launcherURL.path, "--no-browser"]
            process.currentDirectoryURL = projectRootURL
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = standardOutput
            process.standardError = standardError

            do {
                try process.run()

                let deadline = Date().addingTimeInterval(30)
                while Date() < deadline {
                    if let message = try? String(contentsOfFile: urlPath, encoding: .utf8),
                       let url = self.dashboardURL(from: message) {
                        try? fileManager.removeItem(atPath: urlPath)
                        try? fileManager.removeItem(atPath: errorPath)
                        DispatchQueue.main.async {
                            self.revealWhenDashboardLoads = true
                            self.webView.load(URLRequest(url: url))
                        }
                        return
                    }
                    Thread.sleep(forTimeInterval: 0.2)
                }
                let error = (try? String(contentsOfFile: errorPath, encoding: .utf8))
                    ?? "DASHBOARD_START_TIMEOUT"
                self.showLaunchError(message: error)
            } catch {
                self.showLaunchError(message: "DASHBOARD_APP_LAUNCH_FAILED")
            }
        }
    }

    private func startStartupCatchUp(_ projectRootURL: URL) {
        let pythonURL = projectRootURL.appendingPathComponent(".venv/bin/python")
        let runnerURL = projectRootURL.appendingPathComponent("scripts/run_scheduled_sync.py")
        guard FileManager.default.isExecutableFile(atPath: pythonURL.path),
              FileManager.default.fileExists(atPath: runnerURL.path) else { return }
        let process = Process()
        process.executableURL = pythonURL
        process.arguments = [runnerURL.path, "--trigger-type", "catch_up"]
        process.currentDirectoryURL = projectRootURL
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            // Dashboard availability must never depend on the optional
            // background catch-up process.
        }
    }

    private func dashboardURL(from output: String) -> URL? {
        for line in output.split(separator: "\n") {
            let prefix = "Dashboard: "
            if line.hasPrefix(prefix) {
                let value = String(line.dropFirst(prefix.count))
                guard value.hasPrefix("http://127.0.0.1:") else { return nil }
                return URL(string: value)
            }
        }
        return nil
    }

    private func showLaunchError(message: String) {
        let safeMessage = message
            .split(separator: "\n")
            .last
            .map(String.init) ?? "DASHBOARD_APP_LAUNCH_FAILED"
        DispatchQueue.main.async {
            let alert = NSAlert()
            alert.alertStyle = .critical
            alert.messageText = "无法启动本地数据看板"
            alert.informativeText = safeMessage
            alert.addButton(withTitle: "关闭")
            alert.runModal()
            NSApp.terminate(nil)
        }
    }
}

let application = NSApplication.shared
let delegate = DashboardAppDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
