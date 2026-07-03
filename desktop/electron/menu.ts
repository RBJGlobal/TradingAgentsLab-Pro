import {
  app,
  BrowserWindow,
  Menu,
  MenuItemConstructorOptions,
  shell,
} from 'electron';

/** Routes the renderer hash router knows about. */
type Route = 'analyze' | 'watchlist' | 'history' | 'settings';

const SITE_URL = 'https://tradingagentslab.ai';
const SUPPORT_EMAIL = 'support@tradingagentslab.ai';

function send(win: BrowserWindow | null, channel: string, ...args: unknown[]): void {
  if (!win || win.isDestroyed()) return;
  win.webContents.send(channel, ...args);
}

function navTo(win: BrowserWindow | null, route: Route): void {
  send(win, 'menu:navigate', route);
}

function buildMenu(getWin: () => BrowserWindow | null): Menu {
  const isMac = process.platform === 'darwin';

  const fileMenu: MenuItemConstructorOptions = {
    label: 'File',
    submenu: [
      {
        label: 'New analysis',
        accelerator: 'CmdOrCtrl+N',
        click: () => {
          navTo(getWin(), 'analyze');
          send(getWin(), 'menu:new-analysis');
        },
      },
      {
        label: 'Stop streaming',
        accelerator: 'CmdOrCtrl+.',
        click: () => send(getWin(), 'menu:stop-stream'),
      },
      { type: 'separator' },
      isMac ? { role: 'close' } : { role: 'quit' },
    ],
  };

  const navMenu: MenuItemConstructorOptions = {
    label: 'Go',
    submenu: [
      {
        label: 'Analyze',
        accelerator: 'CmdOrCtrl+1',
        click: () => navTo(getWin(), 'analyze'),
      },
      {
        label: 'Watchlist',
        accelerator: 'CmdOrCtrl+2',
        click: () => navTo(getWin(), 'watchlist'),
      },
      {
        label: 'History',
        accelerator: 'CmdOrCtrl+3',
        click: () => navTo(getWin(), 'history'),
      },
      { type: 'separator' },
      {
        label: 'Settings',
        accelerator: 'CmdOrCtrl+,',
        click: () => navTo(getWin(), 'settings'),
      },
    ],
  };

  const editMenu: MenuItemConstructorOptions = {
    label: 'Edit',
    submenu: [
      { role: 'undo' },
      { role: 'redo' },
      { type: 'separator' },
      { role: 'cut' },
      { role: 'copy' },
      { role: 'paste' },
      { role: 'selectAll' },
    ],
  };

  const viewMenu: MenuItemConstructorOptions = {
    label: 'View',
    submenu: [
      { role: 'reload' },
      { role: 'forceReload' },
      { role: 'toggleDevTools' },
      { type: 'separator' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { type: 'separator' },
      { role: 'togglefullscreen' },
    ],
  };

  const windowMenu: MenuItemConstructorOptions = {
    label: 'Window',
    submenu: isMac
      ? [
          { role: 'minimize' },
          { role: 'zoom' },
          { type: 'separator' },
          { role: 'front' },
        ]
      : [{ role: 'minimize' }, { role: 'close' }],
  };

  const helpMenu: MenuItemConstructorOptions = {
    label: 'Help',
    submenu: [
      {
        label: 'Check for Updates…',
        // Opens Settings, where the Updates tab manages app updates. (The old
        // item pinged the upstream open-source repo, which is not meaningful
        // for this product.)
        click: () => navTo(getWin(), 'settings'),
      },
      { type: 'separator' },
      {
        label: 'Visit Trading Agents Lab',
        click: () => shell.openExternal(SITE_URL),
      },
      {
        label: 'Contact Support',
        click: () => shell.openExternal(`mailto:${SUPPORT_EMAIL}`),
      },
      { type: 'separator' },
      {
        label: 'Open Settings',
        click: () => navTo(getWin(), 'settings'),
      },
    ],
  };

  const macAppMenu: MenuItemConstructorOptions = {
    label: app.name,
    submenu: [
      { role: 'about' },
      { type: 'separator' },
      {
        label: 'Settings…',
        accelerator: 'Cmd+,',
        click: () => navTo(getWin(), 'settings'),
      },
      { type: 'separator' },
      { role: 'services' },
      { type: 'separator' },
      { role: 'hide' },
      { role: 'hideOthers' },
      { role: 'unhide' },
      { type: 'separator' },
      { role: 'quit' },
    ],
  };

  const template: MenuItemConstructorOptions[] = isMac
    ? [macAppMenu, fileMenu, editMenu, navMenu, viewMenu, windowMenu, helpMenu]
    : [fileMenu, editMenu, navMenu, viewMenu, windowMenu, helpMenu];

  return Menu.buildFromTemplate(template);
}

export function registerAppMenu(getWin: () => BrowserWindow | null): void {
  Menu.setApplicationMenu(buildMenu(getWin));
}
