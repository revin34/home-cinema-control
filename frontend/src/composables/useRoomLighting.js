import {computed, nextTick, ref, watch} from 'vue'
import {api} from '../api/index.js'

export const LIGHTING_ACTIONS = ['turn_off', 'turn_on', 'none']

// Display-only flag added by the backend sanitizer; never sent back.
const DISPLAY_ONLY_FIELDS = ['home_assistant_token_configured']

export function emptyLighting() {
    return {
        enabled: false,
        home_assistant_url: '',
        home_assistant_token: '',
        entity_ids: [],
        on_playback_start: 'turn_off',
        on_playback_stop: 'turn_on',
        fade_out_seconds: 0,
        fade_in_seconds: 0,
    }
}

export function lightingPayload(lighting) {
    const payload = {...lighting, entity_ids: [...(lighting.entity_ids || [])]}
    for (const field of DISPLAY_ONLY_FIELDS) delete payload[field]
    // An empty token means "keep the stored one": the backend refills it from
    // secrets.json, so never send a blank value that could look like a reset.
    if (!String(payload.home_assistant_token || '').trim()) delete payload.home_assistant_token
    return payload
}

export function lightingReadiness(lighting, tested = false) {
    if (!lighting.enabled) return {status: 'disabled', detail: 'Lighting control disabled (optional)'}
    if (!lighting.home_assistant_url) return {status: 'incomplete', detail: 'Home Assistant URL not set'}
    if (!lighting.home_assistant_token_configured && !String(lighting.home_assistant_token || '').trim()) {
        return {status: 'incomplete', detail: 'Home Assistant token not configured'}
    }
    const count = (lighting.entity_ids || []).length
    if (!count) return {status: 'incomplete', detail: 'No lights selected'}
    return {status: tested ? 'verified' : 'configured', detail: `Home Assistant · ${count} entities`}
}

export function useRoomLighting({configWithSection, saveConfigSection, onReadinessChange}) {
    const lighting = ref(emptyLighting())
    const entities = ref([])
    const entityFilter = ref('')
    const tested = ref(false)
    const testLoading = ref(false)
    const entitiesLoading = ref(false)
    const switchLoading = ref('')

    const state = computed(() => {
        const readiness = lightingReadiness(lighting.value, tested.value)
        if (readiness.status === 'verified') return 'tested'
        return readiness.status
    })

    // Detected entities plus any stored id Home Assistant did not report
    // (renamed/unavailable), so a saved selection is never silently dropped.
    const entityOptions = computed(() => {
        const known = new Map(entities.value.map((entity) => [entity.entity_id, entity]))
        for (const entityId of lighting.value.entity_ids || []) {
            if (!known.has(entityId)) known.set(entityId, {entity_id: entityId, name: entityId, state: ''})
        }
        const filter = entityFilter.value.trim().toLowerCase()
        return [...known.values()].filter((entity) =>
            !filter
            || entity.entity_id.toLowerCase().includes(filter)
            || entity.name.toLowerCase().includes(filter))
    })

    // Only connection settings invalidate a successful test; picking lights
    // afterwards keeps it (the backend verification fingerprint agrees).
    watch(
        () => [
            lighting.value.enabled,
            lighting.value.home_assistant_url,
            lighting.value.home_assistant_token,
        ].join('|'),
        () => {
            tested.value = false
            onReadinessChange?.(lightingReadiness(lighting.value))
        },
    )

    watch(
        () => (lighting.value.entity_ids || []).join(','),
        () => onReadinessChange?.(lightingReadiness(lighting.value, tested.value)),
    )

    function load(config) {
        lighting.value = {...emptyLighting(), ...(config?.lighting || {})}
        lighting.value.home_assistant_token = ''
        tested.value = false
    }

    function isSelected(entityId) {
        return (lighting.value.entity_ids || []).includes(entityId)
    }

    function toggleEntity(entityId) {
        const selected = new Set(lighting.value.entity_ids || [])
        if (selected.has(entityId)) selected.delete(entityId)
        else selected.add(entityId)
        lighting.value.entity_ids = [...selected]
    }

    async function submittedConfig() {
        return configWithSection('lighting', lightingPayload(lighting.value))
    }

    function applySavedLighting(savedLighting) {
        lighting.value = {...emptyLighting(), ...(savedLighting || {}), home_assistant_token: ''}
    }

    async function testConnection() {
        testLoading.value = true
        try {
            const result = await api.testLightingConnection(await submittedConfig())
            if (result?.lighting) applySavedLighting(result.lighting)
            // applySavedLighting retriggers the watcher that resets `tested`;
            // flip it after that pending reset has run.
            await nextTick()
            tested.value = true
            onReadinessChange?.(lightingReadiness(lighting.value, true))
            return result
        } finally {
            testLoading.value = false
        }
    }

    async function detectEntities() {
        entitiesLoading.value = true
        try {
            const result = await api.getLightingEntities(await submittedConfig())
            entities.value = result?.entities || []
            return entities.value
        } finally {
            entitiesLoading.value = false
        }
    }

    async function switchLights(action) {
        switchLoading.value = action
        try {
            const config = await submittedConfig()
            return action === 'turn_on'
                ? await api.lightingTurnOn(config)
                : await api.lightingTurnOff(config)
        } finally {
            switchLoading.value = ''
        }
    }

    async function save() {
        const savedConfig = await saveConfigSection('lighting', lightingPayload(lighting.value))
        const wasTested = tested.value
        applySavedLighting(savedConfig?.lighting)
        await nextTick()
        tested.value = wasTested
        onReadinessChange?.(lightingReadiness(lighting.value, wasTested))
        return savedConfig
    }

    return {
        lighting,
        entities,
        entityFilter,
        entityOptions,
        state,
        tested,
        testLoading,
        entitiesLoading,
        switchLoading,
        load,
        isSelected,
        toggleEntity,
        testConnection,
        detectEntities,
        switchLights,
        save,
    }
}
