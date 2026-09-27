import {computed, nextTick, ref, watch} from 'vue'

const EMPTY_DRAFT = {name: '', source_path: '', player_path: '', protocol: '', verified: false, power_switch_entity_id: '', power_wait_timeout_seconds: null}

// Resolves media_servers.providers[media_servers.active].playback.path_mappings
// from a full config response — the nested shape that replaced the old flat
// config.playback.path_mappings. See
// .agents/specs/2026-06-23-media-server-scoped-paths-libraries-device.md.
function activeProviderPathMappings(config) {
    const activeType = config?.media_servers?.active
    return config?.media_servers?.providers?.[activeType]?.playback?.path_mappings || []
}

export function useMediaPathWorkflow({
                                         api,
                                         defaultProtocol,
                                         isLibraryIntercepted = () => true,
                                         persistRouteMappings,
                                         persistNetworkAccess,
                                         clearSmbCredentials,
                                     }) {
    const mappings = ref([])
    const detectedLibraryPaths = ref([])
    const editing = ref(false)
    const advancedMode = ref(false)
    const selectedKey = ref(null)
    const editIndex = ref(null)
    const form = ref({...EMPTY_DRAFT})
    const originalForm = ref(null)
    const rowErrors = ref({})

    const preview = ref(null)
    const testResult = ref(null)
    const showNav = ref(false)
    const navDirs = ref([])
    const navLoading = ref(false)
    const navError = ref(null)
    const playerSuggestion = ref(null)
    const testLoading = ref(false)
    const powerOnLoading = ref(false)

    let previewTimer = null
    let suggestionTimer = null
    let draftRevision = 0
    let navRevision = 0
    let effectsPaused = false

    const currentProtocol = computed(() => form.value.protocol || defaultProtocol())
    const smbEnabled = computed({
        get: () => currentProtocol.value === 'cifs',
        set: (enabled) => setProtocol(enabled ? 'cifs' : 'nfs'),
    })
    const originalVerified = computed(() => !!originalForm.value?.verified)
    const formDirty = computed(() => {
        if (!editing.value) return false
        const original = originalForm.value || EMPTY_DRAFT
        return ['name', 'source_path', 'player_path', 'protocol'].some(
            (field) => normalizeComparable(form.value[field]) !== normalizeComparable(original[field]),
        )
    })
    const canTest = computed(() =>
        !!(form.value.name && form.value.source_path && hasPlayerPath(form.value.player_path)),
    )
    const canSaveDraft = computed(() =>
        !!(form.value.name && form.value.source_path && hasPlayerPath(form.value.player_path)),
    )

    const detectedRows = computed(() => {
        return detectedLibraryPaths.value.map((lib) => {
            const source = normalizePath(lib.source_path)
            const mappingIndex = mappings.value.findIndex((m) => normalizePath(m.source_path) === source)
            const mapping = mappingIndex >= 0 ? mappings.value[mappingIndex] : null
            const key = rowKey(source)
            return {
                key,
                type: 'detected',
                name: mapping?.name || lib.library_name || source,
                library_name: lib.library_name || '',
                source_path: lib.source_path,
                intercepted: isLibraryIntercepted(lib),
                mapping,
                mappingIndex,
                status: resolveRowStatus(key, mapping, isLibraryIntercepted(lib)),
            }
        })
    })

    const manualRows = computed(() => {
        const detectedSources = new Set(detectedLibraryPaths.value.map((lib) => normalizePath(lib.source_path)))
        return mappings.value
            .map((mapping, index) => ({mapping, index}))
            .filter(({mapping}) => !detectedSources.has(normalizePath(mapping.source_path)))
            .map(({mapping, index}) => {
                const key = `manual:${index}`
                return {
                    key,
                    type: 'manual',
                    name: mapping.name || mapping.source_path,
                    source_path: mapping.source_path,
                    mapping,
                    mappingIndex: index,
                    intercepted: true,
                    status: resolveRowStatus(key, mapping, true),
                }
            })
    })

    const allRows = computed(() => [...detectedRows.value, ...manualRows.value])
    const statusCounts = computed(() => {
        return allRows.value.reduce((counts, row) => {
            counts[row.status] = (counts[row.status] || 0) + 1
            return counts
        }, {verified: 0, pending: 0, stale: 0, unconfigured: 0, error: 0})
    })

    watch([() => form.value.source_path, () => form.value.player_path], () => {
        if (!editing.value || effectsPaused) return
        resetDraftEffects()
        schedulePreview()
        scheduleSuggestion()
    })

    function initialize(config, libraries) {
        mappings.value = [...activeProviderPathMappings(config)]
        detectedLibraryPaths.value = [...libraries]
        if (detectedRows.value.length) {
            selectRow(detectedRows.value[0])
        } else if (manualRows.value.length) {
            selectRow(manualRows.value[0])
        }
    }

    function setDetectedLibraries(libraries) {
        detectedLibraryPaths.value = [...libraries]
        if (!editing.value && detectedRows.value.length) {
            selectRow(detectedRows.value[0])
        }
    }

    function rowKey(sourcePath) {
        return `source:${normalizePath(sourcePath)}`
    }

    function normalizePath(path) {
        return String(path || '').replace(/\\/g, '/').replace(/\/+/g, '/').replace(/\/$/, '')
    }

    function hasPlayerPath(path) {
        const value = String(path || '').trim()
        return value && value !== '/'
    }

    function normalizeComparable(value) {
        return String(value || '').trim()
    }

    function resolveRowStatus(key, mapping, intercepted) {
        if (selectedKey.value === key && editing.value) {
            if (testResult.value) return 'error'
            if (formDirty.value && originalVerified.value) return 'stale'
            if (hasPlayerPath(form.value.player_path) && !(form.value.verified && !formDirty.value)) return 'pending'
            if (form.value.verified && !formDirty.value && !intercepted) return 'not_intercepted'
            if (form.value.verified && !formDirty.value) return 'verified'
        }

        if (rowErrors.value[key]) return 'error'
        if (!mapping) return 'unconfigured'
        if (mapping.verified && !intercepted) return 'not_intercepted'
        if (mapping.verified) return 'verified'
        if (hasPlayerPath(mapping.player_path)) return 'pending'
        return 'unconfigured'
    }

    function pauseDraftEffects(callback) {
        effectsPaused = true
        callback()
        nextTick(() => {
            effectsPaused = false
        })
    }

    function selectRow(row) {
        pauseDraftEffects(() => {
            selectedKey.value = row.key
            advancedMode.value = row.type === 'manual'
            editIndex.value = row.mappingIndex >= 0 ? row.mappingIndex : null
            const protocol = row.mapping?.protocol || defaultProtocol()
            const draft = {
                name: row.mapping?.name || row.name || '',
                source_path: row.mapping?.source_path || row.source_path || '',
                player_path: row.mapping?.player_path || '',
                protocol,
                verified: !!row.mapping?.verified,
                power_switch_entity_id: row.mapping?.power_switch_entity_id || '',
                power_wait_timeout_seconds: row.mapping?.power_wait_timeout_seconds ?? null,
            }
            form.value = draft
            originalForm.value = {...draft}
            resetPanelState()
            editing.value = true
        })
        nextTick(() => {
            if (!form.value.player_path) scheduleSuggestion()
        })
    }

    function newManualMapping() {
        pauseDraftEffects(() => {
            selectedKey.value = 'advanced:new'
            advancedMode.value = true
            editIndex.value = null
            const draft = {...EMPTY_DRAFT, protocol: defaultProtocol()}
            form.value = draft
            originalForm.value = {...draft}
            resetPanelState()
            editing.value = true
        })
        nextTick(() => document.getElementById('path-name')?.focus())
    }

    function resetPanelState() {
        preview.value = null
        testResult.value = null
        playerSuggestion.value = null
        showNav.value = false
        navDirs.value = []
        navError.value = null
        navLoading.value = false
        clearTimeout(previewTimer)
        clearTimeout(suggestionTimer)
        draftRevision += 1
        navRevision += 1
    }

    function resetDraftEffects() {
        preview.value = null
        testResult.value = null
        playerSuggestion.value = null
        clearTimeout(previewTimer)
        clearTimeout(suggestionTimer)
        draftRevision += 1
    }

    function setProtocol(protocol) {
        if (form.value.protocol === protocol) return
        form.value = {
            ...form.value,
            protocol,
            player_path: '',
            verified: false,
        }
        navDirs.value = []
        navError.value = null
        if (showNav.value) navigate('/')
    }

    function schedulePreview() {
        if (!form.value.source_path || !hasPlayerPath(form.value.player_path)) return
        const revision = draftRevision
        const sourcePath = form.value.source_path
        const playerPath = form.value.player_path
        previewTimer = setTimeout(async () => {
            try {
                const result = await api.previewPath({source_path: sourcePath, player_path: playerPath})
                if (revision === draftRevision && sourcePath === form.value.source_path && playerPath === form.value.player_path) {
                    preview.value = result
                }
            } catch {
                if (revision === draftRevision) preview.value = null
            }
        }, 600)
    }

    function scheduleSuggestion() {
        if (!form.value.source_path || hasPlayerPath(form.value.player_path)) return
        if (!mappings.value.some((mapping) => mapping.verified)) return
        const revision = draftRevision
        const sourcePath = form.value.source_path
        suggestionTimer = setTimeout(() => fetchPlayerSuggestion(revision, sourcePath), 500)
    }

    async function fetchPlayerSuggestion(revision, sourcePath) {
        const anchors = mappings.value.filter((mapping) => mapping.verified)
        for (const anchor of anchors) {
            if (revision !== draftRevision || sourcePath !== form.value.source_path || hasPlayerPath(form.value.player_path)) return
            try {
                const results = await api.getPathMappingSuggestions(
                    {source_path: anchor.source_path, share_path: anchor.player_path},
                    [sourcePath],
                )
                if (
                    revision === draftRevision
                    && sourcePath === form.value.source_path
                    && !hasPlayerPath(form.value.player_path)
                    && results[0]?.share_path
                ) {
                    playerSuggestion.value = results[0].share_path
                    return
                }
            } catch {
                // This anchor cannot safely infer the selected library; try the next verified mapping.
            }
        }
    }

    function acceptPlayerSuggestion() {
        if (!playerSuggestion.value) return
        form.value = {...form.value, player_path: playerSuggestion.value, verified: false}
        playerSuggestion.value = null
    }

    async function testPath() {
        testLoading.value = true
        testResult.value = null
        try {
            await api.testPath({
                name: form.value.name,
                source_path: form.value.source_path,
                player_path: form.value.player_path,
                protocol: form.value.protocol || currentProtocol.value,
                verified: form.value.verified,
                power_switch_entity_id: form.value.power_switch_entity_id || '',
                power_wait_timeout_seconds: normalizedPowerWaitTimeout(),
            })
            form.value = {...form.value, verified: true}
            delete rowErrors.value[selectedKey.value]
            await savePath(true)
        } catch (e) {
            form.value = {...form.value, verified: false}
            testResult.value = e.diagnostic || e
            rowErrors.value[selectedKey.value] = testResult.value
            throw e
        } finally {
            testLoading.value = false
        }
    }

    // An empty number input yields '' — send null so the backend default applies.
    function normalizedPowerWaitTimeout() {
        const value = form.value.power_wait_timeout_seconds
        return value === '' || value === undefined ? null : value
    }

    // Wake the NAS behind this path (Home Assistant switch) and wait for it,
    // e.g. before browsing its folders from the OPPO.
    async function powerOnSource() {
        powerOnLoading.value = true
        try {
            return await api.powerOnPath({
                player_path: form.value.player_path,
                protocol: form.value.protocol || currentProtocol.value,
                power_switch_entity_id: form.value.power_switch_entity_id || '',
                power_wait_timeout_seconds: normalizedPowerWaitTimeout(),
            })
        } finally {
            powerOnLoading.value = false
        }
    }

    async function savePath(requireVerified = false) {
        const entry = createEntry(requireVerified)
        const nextMappings = upsertCurrentMapping(entry)
        const savedConfig = await persistRouteMappings(nextMappings)
        applySavedMappings(savedConfig, entry)
        return savedConfig
    }

    async function deleteCurrentMapping() {
        if (editIndex.value === null) return null
        const nextMappings = mappings.value.filter((_, index) => index !== editIndex.value)
        const savedConfig = await persistRouteMappings(nextMappings)
        mappings.value = [...activeProviderPathMappings(savedConfig)]
        editing.value = false
        selectedKey.value = null
        editIndex.value = null
        originalForm.value = null
        return savedConfig
    }

    async function saveNetworkAccess({smbAccessChanged, preMountSmb, username, password}) {
        let nextMappings = smbAccessChanged ? invalidateCifsMappings(mappings.value) : mappings.value
        let entry = null
        if (editing.value && canSaveDraft.value) {
            entry = createEntry(false)
            if (entry.protocol === 'cifs' && smbAccessChanged) entry.verified = false
            nextMappings = upsertCurrentMapping(entry, nextMappings)
        }

        const savedConfig = await persistNetworkAccess({
            preMountSmb,
            username,
            password,
            pathMappings: nextMappings,
        })
        mappings.value = [...activeProviderPathMappings(savedConfig)]
        if (entry) applySavedMappings(savedConfig, entry)
        return savedConfig
    }

    async function clearCredentialsAndInvalidate() {
        await clearSmbCredentials()
        const nextMappings = invalidateCifsMappings(mappings.value)
        const savedConfig = await persistNetworkAccess({
            preMountSmb: null,
            username: '',
            password: '',
            pathMappings: nextMappings,
        })
        mappings.value = [...activeProviderPathMappings(savedConfig)]
        if (editing.value && form.value.protocol === 'cifs' && hasPlayerPath(form.value.player_path)) {
            form.value = {...form.value, verified: false}
            originalForm.value = {...form.value}
        }
        return savedConfig
    }

    function invalidateCifsMappings(items) {
        return items.map((mapping) => (
            mapping.protocol === 'cifs' || (!mapping.protocol && defaultProtocol() === 'cifs')
                ? {...mapping, verified: false}
                : mapping
        ))
    }

    function createEntry(requireVerified) {
        return {
            ...form.value,
            power_wait_timeout_seconds: normalizedPowerWaitTimeout(),
            protocol: form.value.protocol || currentProtocol.value,
            verified: requireVerified ? true : !!form.value.verified && !formDirty.value,
        }
    }

    function upsertCurrentMapping(entry, baseMappings = mappings.value) {
        const nextMappings = [...baseMappings]
        if (editIndex.value !== null) {
            nextMappings[editIndex.value] = entry
        } else {
            nextMappings.push(entry)
        }
        return nextMappings
    }

    function applySavedMappings(savedConfig, entry) {
        mappings.value = [...activeProviderPathMappings(savedConfig)]
        const nextIndex = mappings.value.findIndex((mapping) => normalizePath(mapping.source_path) === normalizePath(entry.source_path))
        editIndex.value = nextIndex >= 0 ? nextIndex : editIndex.value
        selectedKey.value = advancedMode.value ? `manual:${editIndex.value}` : rowKey(entry.source_path)
        form.value = {...entry}
        originalForm.value = {...entry}
        testResult.value = null
        delete rowErrors.value[selectedKey.value]
    }

    async function toggleNav() {
        showNav.value = !showNav.value
        if (showNav.value) {
            await navigate(form.value.player_path || '/')
        } else {
            navError.value = null
            navLoading.value = false
        }
    }

    async function navigate(path) {
        const revision = ++navRevision
        navLoading.value = true
        navError.value = null
        try {
            const dirs = await api.navigatePath(path || '/', form.value.protocol || currentProtocol.value)
            if (revision === navRevision) navDirs.value = dirs
        } catch (e) {
            if (revision === navRevision) {
                navDirs.value = []
                navError.value = e
            }
        } finally {
            if (revision === navRevision) navLoading.value = false
        }
    }

    async function navigateToFolder(name) {
        let current = form.value.player_path.replace(/\\/g, '/').replace(/\/+/g, '/')
        if (name === '..') {
            const idx = current.lastIndexOf('/')
            current = idx > 0 ? current.substring(0, idx) : '/'
        } else {
            current = current === '/' ? '/' + name : current + '/' + name
        }
        form.value = {...form.value, player_path: current, verified: false}
        await navigate(current)
    }

    return {
        editing,
        advancedMode,
        selectedKey,
        editIndex,
        form,
        originalVerified,
        formDirty,
        preview,
        testResult,
        showNav,
        navDirs,
        navLoading,
        navError,
        playerSuggestion,
        testLoading,
        powerOnLoading,
        currentProtocol,
        smbEnabled,
        canTest,
        canSaveDraft,
        detectedRows,
        manualRows,
        allRows,
        statusCounts,
        initialize,
        setDetectedLibraries,
        selectRow,
        newManualMapping,
        acceptPlayerSuggestion,
        testPath,
        powerOnSource,
        savePath,
        deleteCurrentMapping,
        saveNetworkAccess,
        clearCredentialsAndInvalidate,
        toggleNav,
        navigateToFolder,
    }
}
