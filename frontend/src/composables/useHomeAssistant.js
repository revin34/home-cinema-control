import {computed, nextTick, ref, watch} from 'vue'
import {api} from '../api/index.js'

// Display-only flag added by the backend sanitizer; never sent back.
const DISPLAY_ONLY_FIELDS = ['token_configured']

export function emptyHomeAssistant() {
    return {url: '', token: ''}
}

export function homeAssistantPayload(homeAssistant) {
    const payload = {...homeAssistant}
    for (const field of DISPLAY_ONLY_FIELDS) delete payload[field]
    // An empty token means "keep the stored one": the backend refills it from
    // secrets.json, so never send a blank value that could look like a reset.
    if (!String(payload.token || '').trim()) delete payload.token
    return payload
}

export function homeAssistantConfigured(homeAssistant) {
    return Boolean(
        homeAssistant?.url
        && (homeAssistant.token_configured || String(homeAssistant.token || '').trim()),
    )
}

export function homeAssistantReadiness(homeAssistant, tested = false) {
    if (!homeAssistant.url) return {status: 'disabled', detail: 'Home Assistant not configured (optional)'}
    if (!homeAssistantConfigured(homeAssistant)) {
        return {status: 'incomplete', detail: 'Home Assistant token not configured'}
    }
    return {status: tested ? 'verified' : 'configured', detail: homeAssistant.url}
}

export function useHomeAssistant({configWithSection, saveConfigSection, onReadinessChange}) {
    const homeAssistant = ref(emptyHomeAssistant())
    const tested = ref(false)
    const testLoading = ref(false)

    const configured = computed(() => homeAssistantConfigured(homeAssistant.value))
    const state = computed(() => {
        const readiness = homeAssistantReadiness(homeAssistant.value, tested.value)
        return readiness.status === 'verified' ? 'tested' : readiness.status
    })

    watch(
        () => [homeAssistant.value.url, homeAssistant.value.token].join('|'),
        () => {
            tested.value = false
            onReadinessChange?.(homeAssistantReadiness(homeAssistant.value))
        },
    )

    function load(config) {
        homeAssistant.value = {...emptyHomeAssistant(), ...(config?.home_assistant || {}), token: ''}
        tested.value = false
    }

    function applySaved(saved) {
        homeAssistant.value = {...emptyHomeAssistant(), ...(saved || {}), token: ''}
    }

    async function testConnection() {
        testLoading.value = true
        try {
            const result = await api.testHomeAssistantConnection(
                await configWithSection('home_assistant', homeAssistantPayload(homeAssistant.value)),
            )
            if (result?.home_assistant) applySaved(result.home_assistant)
            // applySaved retriggers the watcher that resets `tested`; flip it
            // after that pending reset has run.
            await nextTick()
            tested.value = true
            onReadinessChange?.(homeAssistantReadiness(homeAssistant.value, true))
            return result
        } finally {
            testLoading.value = false
        }
    }

    async function save() {
        const savedConfig = await saveConfigSection('home_assistant', homeAssistantPayload(homeAssistant.value))
        const wasTested = tested.value
        applySaved(savedConfig?.home_assistant)
        await nextTick()
        tested.value = wasTested
        onReadinessChange?.(homeAssistantReadiness(homeAssistant.value, wasTested))
        return savedConfig
    }

    return {homeAssistant, configured, state, tested, testLoading, load, testConnection, save}
}
