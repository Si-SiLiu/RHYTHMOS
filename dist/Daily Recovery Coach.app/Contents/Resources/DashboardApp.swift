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
        super.keyDown(with: event)
    }
}

final class DashboardAppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var keyEventMonitor: Any?

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
        window.title = "Daily Recovery Coach"
        window.center()
        window.setFrameAutosaveName("DailyRecoveryCoachWindow")

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: frame, configuration: configuration)
        webView.navigationDelegate = self
        window.contentView = webView
        showLoadingPage()

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startDashboard()
    }

    private func installQuitShortcut() {
        keyEventMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let key = event.charactersIgnoringModifiers?.lowercased()
            if modifiers == [.command] && key == "q" {
                NSApp.terminate(nil)
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
        let appMenuItem = NSMenuItem(title: "Daily Recovery Coach", action: nil, keyEquivalent: "")
        let appMenu = NSMenu()
        let quitItem = NSMenuItem(
            title: "退出 Daily Recovery Coach",
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

    private func showLoadingPage() {
        let html = """
        <!doctype html>
        <html lang="zh-CN">
        <meta charset="utf-8">
        <style>
          body { font-family: -apple-system; display: grid; place-items: center;
                 height: 100vh; margin: 0; background: #f6f8fb; color: #243447; }
          main { text-align: center; }
          .dot { display: inline-block; animation: pulse 1.2s infinite; }
          @keyframes pulse { 50% { opacity: .25; } }
        </style>
        <main><h2>Daily Recovery Coach</h2>
        <p class="dot">正在启动本地数据看板…</p></main>
        </html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    private func startDashboard() {
        DispatchQueue.global(qos: .userInitiated).async {
            let fileManager = FileManager.default
            let uid = getuid()
            let urlPath = "/tmp/daily-recovery-coach-url-\(uid).txt"
            let errorPath = "/tmp/daily-recovery-coach-error-\(uid).txt"
            let commandPath = "/tmp/daily-recovery-coach-launch-\(uid).command"
            try? fileManager.removeItem(atPath: urlPath)
            try? fileManager.removeItem(atPath: errorPath)
            try? fileManager.removeItem(atPath: commandPath)
            let projectRoot = "/Users/liuxi/Documents/Daily·Recovery·Coach"
            let command = """
            #!/bin/zsh
            '\(projectRoot)/.venv/bin/python' '\(projectRoot)/src/dashboard_launcher.py' --no-browser > '\(urlPath)' 2> '\(errorPath)'
            """
            do {
                try command.write(toFile: commandPath, atomically: true, encoding: .utf8)
                try fileManager.setAttributes(
                    [.posixPermissions: 0o700], ofItemAtPath: commandPath
                )
            } catch {
                self.showLaunchError(message: "DASHBOARD_HELPER_WRITE_FAILED")
                return
            }
            let process = Process()
            // macOS protects Documents/Desktop access for Finder-launched GUI
            // children. Terminal already owns the user's local shell permission,
            // so open the short helper there, hidden and in the background.
            process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
            process.arguments = ["-g", "-j", "-a", "Terminal", commandPath]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice

            do {
                try process.run()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else {
                    self.showLaunchError(message: "DASHBOARD_TERMINAL_OPEN_FAILED")
                    return
                }

                let deadline = Date().addingTimeInterval(30)
                while Date() < deadline {
                    if let message = try? String(contentsOfFile: urlPath, encoding: .utf8),
                       let url = self.dashboardURL(from: message) {
                        try? fileManager.removeItem(atPath: urlPath)
                        try? fileManager.removeItem(atPath: errorPath)
                        DispatchQueue.main.async {
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
