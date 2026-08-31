# RHYTHMOS canonical workspace

- Treat `/Users/liuxi/Documents/RHYTHMOS` as the sole source and development root for future RHYTHMOS work.
- Keep newly created RHYTHMOS source, tests, docs, assets, and build support files inside this root.
- Use `/Users/liuxi/Documents/RHYTHMOS/dist/RHYTHMOS.app` as the only supported macOS application build output.
- Do not create or maintain a second RHYTHMOS desktop application under another worktree or output directory.
- Preserve existing user data in `data/`; never replace, reset, or delete it as part of an application rebuild.
