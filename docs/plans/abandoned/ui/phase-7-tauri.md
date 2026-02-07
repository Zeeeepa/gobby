# Phase 7: Tauri Native Wrapper

> **Framework:** Tauri 2.0
> **Goal:** Native desktop app with system tray
> **Depends on:** Phase 6 (PWA features stabilized)

## 7.1 Tauri Setup

### 7.1.1 Project Initialization

- [ ] Install Tauri CLI: `npm install -D @tauri-apps/cli`
- [ ] Initialize Tauri in ui/: `npx tauri init`
- [ ] Configure tauri.conf.json with app metadata
- [ ] Set app identifier: `com.gobby.dashboard`
- [ ] Configure window settings (size, resizable, decorations)

### 7.1.2 Build Configuration

- [ ] Configure build for macOS (universal binary)
- [ ] Configure build for Windows (x64, arm64)
- [ ] Configure build for Linux (AppImage, deb)
- [ ] Set up Rust toolchain requirements
- [ ] Add build scripts to package.json

### 7.1.3 Development Setup

- [ ] Configure dev server URL in tauri.conf.json
- [ ] Add `tauri:dev` script for hot reload
- [ ] Set up source map for debugging
- [ ] Configure console logging

## 7.2 App Signing

### 7.2.1 macOS Code Signing

- [ ] Obtain Apple Developer certificate
- [ ] Configure signing identity in tauri.conf.json
- [ ] Set up entitlements file
- [ ] Configure notarization (Apple notary service)
- [ ] Test Gatekeeper approval

### 7.2.2 Windows Signing

- [ ] Obtain code signing certificate (EV recommended)
- [ ] Configure signtool in build process
- [ ] Test SmartScreen reputation
- [ ] Configure timestamp server

### 7.2.3 Linux Signing

- [ ] Set up GPG key for signing
- [ ] Sign AppImage
- [ ] Configure apt repository signing (for deb)

## 7.3 System Tray

### 7.3.1 Tray Setup

- [ ] Configure system tray in tauri.conf.json
- [ ] Create tray icon (supports dark/light mode)
- [ ] Set default icon state (connected/disconnected)
- [ ] Handle tray icon click (show/hide window)

### 7.3.2 Tray Menu

- [ ] Create tray menu with items:
  - [ ] "Open Dashboard" - shows main window
  - [ ] "Quick Status" - submenu with agent counts
  - [ ] Separator
  - [ ] "Start Daemon" - if not running
  - [ ] "Stop Daemon" - if running
  - [ ] Separator
  - [ ] "Settings" - opens settings view
  - [ ] "Quit" - closes app

### 7.3.3 Tray Status

- [ ] Update icon based on daemon connection
- [ ] Show agent count in tooltip
- [ ] Animate icon when agents running
- [ ] Badge with notification count (macOS)

## 7.4 Global Hotkey

### 7.4.1 Hotkey Registration

- [ ] Register global hotkey (Cmd+Shift+G / Ctrl+Shift+G)
- [ ] Show/hide window on hotkey
- [ ] Focus search on show
- [ ] Handle conflicts with other apps

### 7.4.2 Quick Actions

- [ ] Cmd+Shift+T: Quick task creation
- [ ] Cmd+Shift+A: Show agents
- [ ] Cmd+Shift+S: Show sessions
- [ ] Configure shortcuts in settings

## 7.5 Native Notifications

### 7.5.1 Notification Integration

- [ ] Replace web toasts with native notifications
- [ ] Use system notification center
- [ ] Add notification sound (configurable)
- [ ] Support notification actions (buttons)

### 7.5.2 Notification Actions

- [ ] "View Agent" - opens agent detail
- [ ] "Cancel" - cancels running agent
- [ ] "Dismiss" - closes notification
- [ ] Handle action clicks when app is closed

### 7.5.3 Notification Preferences

- [ ] Toggle notifications in settings
- [ ] Per-type toggles (agent, task, error)
- [ ] Do Not Disturb integration
- [ ] Sound preferences

## 7.6 Auto-Updater

### 7.6.1 Update Configuration

- [ ] Configure update server URL
- [ ] Set up update checking interval
- [ ] Handle update download progress
- [ ] Configure restart behavior

### 7.6.2 Update Flow

- [ ] Check for updates on launch
- [ ] Show update available notification
- [ ] Download in background
- [ ] Prompt to restart and update
- [ ] Handle update errors

### 7.6.3 Release Infrastructure

- [ ] Set up GitHub Releases for distribution
- [ ] Create release workflow (GitHub Actions)
- [ ] Generate release notes from commits
- [ ] Upload signed artifacts

## 7.7 Distribution

### 7.7.1 macOS Distribution

- [ ] Create DMG installer with background image
- [ ] Configure drag-to-Applications layout
- [ ] Set up Sparkle/Tauri updater feed
- [ ] Distribute via GitHub Releases
- [ ] Optional: Mac App Store submission

### 7.7.2 Windows Distribution

- [ ] Create MSI installer (via WiX)
- [ ] Create portable EXE option
- [ ] Configure start menu shortcuts
- [ ] Set up winget manifest
- [ ] Optional: Microsoft Store submission

### 7.7.3 Linux Distribution

- [ ] Create AppImage (universal)
- [ ] Create .deb package
- [ ] Create Flatpak manifest
- [ ] Set up PPA repository (optional)
- [ ] Document manual installation

## 7.8 Deep Linking

### 7.8.1 URL Scheme

- [ ] Register `gobby://` URL scheme
- [ ] Handle `gobby://task/{id}` - opens task
- [ ] Handle `gobby://agent/{id}` - opens agent
- [ ] Handle `gobby://session/{id}` - opens session

### 7.8.2 Integration

- [ ] CLI can open URLs in app
- [ ] Web can trigger app open
- [ ] Handle URL when app is closed

## 7.9 Performance

### 7.9.1 Startup Optimization

- [ ] Minimize bundle size (target <10MB)
- [ ] Lazy load views
- [ ] Cache daemon connection
- [ ] Show skeleton immediately

### 7.9.2 Memory Optimization

- [ ] Monitor memory usage
- [ ] Clean up unused resources
- [ ] Limit cached data
- [ ] Profile with Instruments/perf
