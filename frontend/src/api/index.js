const BASE = '/api/v1'

function detailToMessage(detail) {
    if (Array.isArray(detail)) {
        return detail
            .map(item => (item && typeof item === 'object' ? item.msg || JSON.stringify(item) : String(item)))
            .join('; ')
    }
    return detail
}

function shouldNotifyConfigChanged(method, path) {
    if (method === 'PATCH' && path.startsWith('/config/')) return true
    if (method !== 'POST') return false
    return path === '/media-server/token'
        || path === '/media-server/check'
        || path === '/config/smb/clear'
        || path === '/oppo/check'
        || path === '/tv/test-connection'
        || path === '/tv/switch-input'
        || path === '/tv/restore-input'
        || path === '/av/sources'
        || path === '/av/power-on'
        || path === '/av/power-off'
        || path === '/av/switch-input'
        || path === '/home-assistant/test-connection'
        || path === '/migration/apply'
        || path === '/migration/skip'
        || path === '/migration/import-legacy'
        || path === '/telemetry/enable'
        || path === '/telemetry/disable'
        || path === '/telemetry/clear-queue'
        || path === '/telemetry/reset-installation-id'
}

function notifyConfigChanged(method, path) {
    if (!shouldNotifyConfigChanged(method, path) || typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('hcc:config-saved'))
}

async function request(method, path, body) {
    const opts = {method, headers: {}}
    if (body !== undefined) {
        opts.headers['Content-Type'] = 'application/json'
        opts.body = JSON.stringify(body)
    }
    const res = await fetch(`${BASE}${path}`, opts)
    if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        const err = new Error(detailToMessage(data.detail) || `Error ${res.status}`)
        err.status = res.status
        if (data.diagnostic) err.diagnostic = data.diagnostic
        throw err
    }
    const ct = res.headers.get('content-type') || ''
    const data = ct.includes('application/json') ? await res.json() : await res.text()
    notifyConfigChanged(method, path)
    return data
}

export const api = {
    // config
    getConfig: () => request('GET', '/config'),
    getConfigWithLibraries: () => request('GET', '/config/libraries'),
    getConfigWithDevices: () => request('GET', '/config/devices'),
    saveConfigSection: (section, body) => request('PATCH', `/config/${section}`, body),

    // system
    getState: () => request('GET', '/state'),
    getLang: () => request('GET', '/lang'),
    getLogs: () => request('GET', '/logs'),
    clearDiagnostics: () => request('POST', '/diagnostics/clear'),
    getSupportSummary: () => request('GET', '/support/summary'),
    getSupportReport: (lines) => request('GET', `/support/report${lines ? `?lines=${lines}` : ''}`),
    restart: () => request('POST', '/restart'),

    // version
    checkVersion: (includePrerelease = false, force = false) => request('GET', `/version/check?include_prerelease=${includePrerelease}&force=${force}`),
    updateVersion: () => request('POST', '/version/update'),
    rollbackVersion: () => request('GET', '/version/rollback'),

    // migration
    getMigrationStatus: () => request('GET', '/migration/status'),
    applyMigration: () => request('POST', '/migration/apply'),
    skipMigration: () => request('POST', '/migration/skip'),
    importLegacyConfig: (config) => request('POST', '/migration/import-legacy', config),

    // media server (provider-neutral: Emby or Jellyfin)
    configureMediaServerToken: (config, credentials, options = {}) =>
        request('POST', '/media-server/token', {config, credentials, ...options}),
    checkMediaServer: (config) => request('POST', '/media-server/check', config),

    // oppo
    checkOppo: (config) => request('POST', '/oppo/check', config),
    sendKey: (key) => request('GET', `/oppo/key/${key}`),
    getOppoAdvancedDefaults: () => request('GET', '/oppo/advanced-defaults'),

    // paths
    refreshPaths: () => request('GET', '/paths/refresh'),
    previewPath: (pathData) => request('POST', '/paths/preview', pathData),
    testPath: (pathData) => request('POST', '/paths/test', pathData),
    powerOnPath: (pathData) => request('POST', '/paths/power-on', pathData),
    navigatePath: (path, protocol) => request('POST', '/paths/navigate', {path, protocol}),

    // readiness
    getConfigReadiness: () => request('GET', '/config/readiness'),
    clearSmbCredentials: () => request('POST', '/config/smb/clear'),

    // media-server discovery
    getLibraryPaths: () => request('GET', '/media-server/library-paths'),
    getPathMappingSuggestions: (anchor, candidates) =>
        request('POST', '/path-mapping-suggestions', {anchor, candidates}),

    // network
    discoverDevices: () => request('GET', '/network/devices'),

    // telemetry
    getTelemetryStatus: () => request('GET', '/telemetry'),
    enableTelemetry: () => request('POST', '/telemetry/enable'),
    disableTelemetry: (resetIdentity = false) =>
        request('POST', '/telemetry/disable', {reset_identity: resetIdentity}),
    clearTelemetryQueue: () => request('POST', '/telemetry/clear-queue'),
    resetTelemetryInstallationId: () => request('POST', '/telemetry/reset-installation-id'),
    submitRoadmapInterest: (interests, comment) =>
        request('POST', '/telemetry/roadmap-interest', {interests, comment: comment || ''}),
    dismissTelemetryPrompt: () => request('POST', '/telemetry/dismiss-prompt'),

    // tv
    testTvConnection: (config) => request('POST', '/tv/test-connection', config),
    getTvSources: (config) => request('POST', '/tv/sources', config),
    getTvApps: (config) => request('POST', '/tv/apps', config),
    tvSwitchInput: (config) => request('POST', '/tv/switch-input', config),
    tvRestoreInput: (config) => request('POST', '/tv/restore-input', config),

    // av
    getAvSources: (config) => request('POST', '/av/sources', config),
    avPowerOn: (config) => request('POST', '/av/power-on', config),
    avPowerOff: (config) => request('POST', '/av/power-off', config),
    avSwitchInput: (config) => request('POST', '/av/switch-input', config),

    // Home Assistant
    testHomeAssistantConnection: (config) => request('POST', '/home-assistant/test-connection', config),
    getHomeAssistantEntities: (config, domains) =>
        request('POST', `/home-assistant/entities?domains=${encodeURIComponent(domains.join(','))}`, config),

    // lighting (through Home Assistant)
    lightingTurnOn: (config) => request('POST', '/lighting/turn-on', config),
    lightingTurnOff: (config) => request('POST', '/lighting/turn-off', config),
}
