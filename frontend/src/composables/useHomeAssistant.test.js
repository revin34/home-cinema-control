import {describe, expect, it, vi} from 'vitest'
import {nextTick} from 'vue'

vi.mock('../api/index.js', () => ({
    api: {
        testHomeAssistantConnection: vi.fn(),
    },
}))

const {api} = await import('../api/index.js')
const {
    homeAssistantConfigured,
    homeAssistantPayload,
    homeAssistantReadiness,
    useHomeAssistant,
} = await import('./useHomeAssistant.js')

function setup() {
    const configWithSection = vi.fn(async (section, value) => ({[section]: value}))
    const saveConfigSection = vi.fn(async (section, value) => ({
        [section]: {...value, token_configured: true},
    }))
    const onReadinessChange = vi.fn()
    const homeAssistant = useHomeAssistant({configWithSection, saveConfigSection, onReadinessChange})
    return {homeAssistant, configWithSection, saveConfigSection, onReadinessChange}
}

describe('homeAssistantPayload', () => {
    it('drops display-only flags and a blank token', () => {
        expect(homeAssistantPayload({url: 'http://ha', token: ' ', token_configured: true}))
            .toEqual({url: 'http://ha'})
    })

    it('keeps a newly typed token', () => {
        expect(homeAssistantPayload({url: 'http://ha', token: 'abc'}).token).toBe('abc')
    })
})

describe('homeAssistantReadiness', () => {
    it('is optional when no URL is set', () => {
        expect(homeAssistantReadiness({url: ''}).status).toBe('disabled')
    })

    it('needs a token', () => {
        expect(homeAssistantReadiness({url: 'http://ha'}).status).toBe('incomplete')
        expect(homeAssistantConfigured({url: 'http://ha', token: 'abc'})).toBe(true)
        expect(homeAssistantConfigured({url: 'http://ha', token_configured: true})).toBe(true)
    })

    it('reports verified after a successful test', () => {
        expect(homeAssistantReadiness({url: 'http://ha', token_configured: true}, true).status).toBe('verified')
    })
})

describe('useHomeAssistant', () => {
    it('loads config without exposing a token value', () => {
        const {homeAssistant} = setup()

        homeAssistant.load({home_assistant: {url: 'http://ha', token_configured: true}})

        expect(homeAssistant.homeAssistant.value.token).toBe('')
        expect(homeAssistant.configured.value).toBe(true)
    })

    it('marks the card tested after a successful connection test', async () => {
        const {homeAssistant, onReadinessChange} = setup()
        homeAssistant.load({home_assistant: {url: 'http://ha'}})
        homeAssistant.homeAssistant.value.token = 'abc'
        api.testHomeAssistantConnection.mockResolvedValueOnce({
            home_assistant: {url: 'http://ha', token_configured: true},
        })

        await homeAssistant.testConnection()

        expect(api.testHomeAssistantConnection.mock.calls[0][0].home_assistant.token).toBe('abc')
        expect(homeAssistant.homeAssistant.value.token).toBe('')
        expect(homeAssistant.state.value).toBe('tested')
        expect(onReadinessChange).toHaveBeenLastCalledWith(expect.objectContaining({status: 'verified'}))
    })

    it('changing the URL after a test clears the tested state', async () => {
        const {homeAssistant} = setup()
        homeAssistant.load({home_assistant: {url: 'http://ha', token_configured: true}})
        api.testHomeAssistantConnection.mockResolvedValueOnce({
            home_assistant: {url: 'http://ha', token_configured: true},
        })
        await homeAssistant.testConnection()

        homeAssistant.homeAssistant.value.url = 'http://other'
        await nextTick()

        expect(homeAssistant.tested.value).toBe(false)
    })

    it('saves through the home_assistant section without a blank token', async () => {
        const {homeAssistant, saveConfigSection} = setup()
        homeAssistant.load({home_assistant: {url: 'http://ha', token_configured: true}})

        await homeAssistant.save()

        expect(saveConfigSection).toHaveBeenCalledWith('home_assistant', {url: 'http://ha'})
        expect(homeAssistant.homeAssistant.value.token_configured).toBe(true)
    })
})
