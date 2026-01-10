# Phase 6: Mobile PWA

> **Framework:** Next.js PWA + Service Worker
> **Goal:** Remote agent monitoring from phone
> **Depends on:** Phase 5 (core web features complete)

## 6.1 PWA Infrastructure

### 6.1.1 Service Worker Setup

- [ ] Install next-pwa: `npm install next-pwa`
- [ ] Configure service worker in next.config.js
- [ ] Set up caching strategies (network-first for API, cache-first for assets)
- [ ] Handle offline fallback page
- [ ] Add background sync for failed mutations

### 6.1.2 Web App Manifest

- [ ] Create `public/manifest.json` with app metadata
- [ ] Add multiple icon sizes (192x192, 512x512)
- [ ] Set display: standalone
- [ ] Configure theme_color from design system
- [ ] Set start_url to dashboard

### 6.1.3 Install Prompt

- [ ] Create `InstallBanner` component for iOS/Android
- [ ] Detect install capability (beforeinstallprompt event)
- [ ] Show install instructions for iOS (Add to Home Screen)
- [ ] Track installation for analytics

## 6.2 Push Notifications

### 6.2.1 Notification Setup

- [ ] Set up web push with VAPID keys
- [ ] Create notification permission request flow
- [ ] Store push subscription in daemon
- [ ] Handle notification click (deep link to relevant view)

### 6.2.2 Notification Types

- [ ] Agent completed notification
- [ ] Agent failed notification
- [ ] Task assigned notification
- [ ] Worktree conflict notification
- [ ] Daemon disconnected notification

### 6.2.3 Notification Preferences

- [ ] Create notification settings page
- [ ] Toggle by notification type
- [ ] Set quiet hours
- [ ] Per-project preferences

## 6.3 Mobile-Optimized Views

### 6.3.1 Mobile Dashboard

- [ ] Create mobile-specific dashboard layout
- [ ] Show agent status prominently (hero section)
- [ ] Quick action cards (tap to cancel, tap to view)
- [ ] Swipe to refresh
- [ ] Pull-down for agent count

### 6.3.2 Agent Status View

- [ ] Create `MobileAgentList` component
- [ ] Large touch targets (min 44px)
- [ ] Swipe left to cancel
- [ ] Tap to expand details
- [ ] Status color coding

### 6.3.3 Task Quick View

- [ ] Create `MobileTaskList` component
- [ ] Show ready tasks only by default
- [ ] Tap task to copy ID to clipboard
- [ ] Swipe right to mark in progress
- [ ] Simple filters (type, priority)

### 6.3.4 Session Summary

- [ ] Create `MobileSessionSummary` component
- [ ] Show today's cost prominently
- [ ] Token usage breakdown by provider
- [ ] Tap for detailed breakdown

## 6.4 Responsive Design

### 6.4.1 Breakpoints

- [ ] Define breakpoints: 320px (phone), 768px (tablet), 1024px (desktop)
- [ ] Use Tailwind responsive prefixes
- [ ] Test on common device sizes
- [ ] Handle orientation changes

### 6.4.2 Mobile Navigation

- [ ] Convert sidebar to bottom tab bar on mobile
- [ ] Show 4 main tabs: Agents, Tasks, Sessions, More
- [ ] "More" opens full navigation sheet
- [ ] Hide breadcrumbs on mobile

### 6.4.3 Touch Interactions

- [ ] Implement swipe gestures (cancel agent, copy task ID)
- [ ] Add haptic feedback on actions
- [ ] Long-press for context menu
- [ ] Pull-to-refresh on lists

## 6.5 Offline Support

### 6.5.1 Offline Data

- [ ] Cache last known agent states
- [ ] Cache task list snapshot
- [ ] Cache session history
- [ ] Show stale data indicator

### 6.5.2 Offline Actions

- [ ] Queue cancel agent requests
- [ ] Queue task status updates
- [ ] Show pending actions badge
- [ ] Sync on reconnection

### 6.5.3 Connection Status

- [ ] Show connection status in header
- [ ] Toast on connection lost
- [ ] Toast on connection restored
- [ ] Auto-retry connection

## 6.6 Remote Access

### 6.6.1 Tunnel Command

- [ ] Create `gobby tunnel start` CLI command
- [ ] Use Cloudflare Quick Tunnels (trycloudflare.com)
- [ ] Display tunnel URL in terminal
- [ ] Generate QR code for mobile setup

### 6.6.2 QR Code Setup

- [ ] Generate QR code containing tunnel URL + auth token
- [ ] Display in TUI and Web UI
- [ ] Mobile app scans and saves configuration
- [ ] Test connection before saving

### 6.6.3 Authentication

- [ ] Generate random auth token on tunnel start
- [ ] Store token in daemon config
- [ ] Validate token on all API requests
- [ ] Token refresh mechanism
- [ ] Revoke token on tunnel stop

### 6.6.4 Connection Management

- [ ] Save multiple tunnel configurations
- [ ] Show connection status per tunnel
- [ ] Reconnect to last used tunnel
- [ ] Clear saved tunnels

## 6.7 Battery Optimization

- [ ] Reduce WebSocket polling when in background
- [ ] Defer non-critical updates
- [ ] Batch notification checks
- [ ] Use visibility API to pause updates
