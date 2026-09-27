import {computed, ref, watch} from 'vue'
import {api} from '../api/index.js'

export const LIGHTING_ACTIONS = ['turn_off', 'turn_on', 'none']
export const LIGHTING_ENTITY_DOMAINS = ['light', 'switch']

export function emptyLighting() {
    return {
        enabled: false,
        entity_ids: [],
        on_playback_start: 'turn_off',
        on_playback_stop: 'turn_on',
        fade_out_seconds: 0,
        fade_in_seconds: 0,
    }
}

export function lightingPayload(lighting) {
    return {...lighting, entity_ids: [...(lighting.entity_ids || [])]}
}

export function lightingReadiness(lighting, homeAssistantReady = true) {
    if (!lighting.enabled) return {status: 'disabled', detail: 'Lighting control disabled (optional)'}
    if (!homeAssistantReady) return {status: 'incomplete', detail: 'Home Assistant not configured'}
    const count = (lighting.entity_ids || []).length
    if (!count) return {status: 'incomplete', detail: 'No lights selected'}
    return {status: 'configured', detail: `Home Assistant · ${count} entities`}
}

export function useRoomLighting({
                                    configWithSection,
                                    saveConfigSection,
                                    homeAssistantReady = () => true,
                                    onReadinessChange,
                                }) {
    const lighting = ref(emptyLighting())
    const entities = ref([])
    const entityFilter = ref('')
    const entitiesLoading = ref(false)
    const switchLoading = ref('')

    const readiness = computed(() => lightingReadiness(lighting.value, homeAssistantReady()))
    const state = computed(() => readiness.value.status)

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

    watch(readiness, (value) => onReadinessChange?.(value))

    function load(config) {
        lighting.value = {...emptyLighting(), ...(config?.lighting || {})}
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

    async function detectEntities() {
        entitiesLoading.value = true
        try {
            const result = await api.getHomeAssistantEntities(await submittedConfig(), LIGHTING_ENTITY_DOMAINS)
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
        lighting.value = {...emptyLighting(), ...(savedConfig?.lighting || {})}
        return savedConfig
    }

    return {
        lighting,
        entities,
        entityFilter,
        entityOptions,
        state,
        entitiesLoading,
        switchLoading,
        load,
        isSelected,
        toggleEntity,
        detectEntities,
        switchLights,
        save,
    }
}
