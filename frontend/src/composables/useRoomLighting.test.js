import {describe, expect, it, vi} from 'vitest'

vi.mock('../api/index.js', () => ({
    api: {
        testLightingConnection: vi.fn(),
        getLightingEntities: vi.fn(),
        lightingTurnOn: vi.fn(),
        lightingTurnOff: vi.fn(),
    },
}))

const {api} = await import('../api/index.js')
const {lightingPayload, lightingReadiness, useRoomLighting} = await import('./useRoomLighting.js')

function setup() {
    const configWithSection = vi.fn(async (section, value) => ({[section]: value}))
    const saveConfigSection = vi.fn(async (section, value) => ({
        [section]: {...value, home_assistant_token_configured: true},
    }))
    const onReadinessChange = vi.fn()
    const lighting = useRoomLighting({configWithSection, saveConfigSection, onReadinessChange})
    return {lighting, configWithSection, saveConfigSection, onReadinessChange}
}

describe('lightingPayload', () => {
    it('drops display-only flags and a blank token', () => {
        expect(lightingPayload({
            enabled: true,
            home_assistant_token: '  ',
            home_assistant_token_configured: true,
            entity_ids: ['light.ceiling'],
        })).toEqual({enabled: true, entity_ids: ['light.ceiling']})
    })

    it('keeps a newly typed token', () => {
        expect(lightingPayload({home_assistant_token: 'abc', entity_ids: []}).home_assistant_token).toBe('abc')
    })
})

describe('lightingReadiness', () => {
    const complete = {
        enabled: true,
        home_assistant_url: 'http://ha.local:8123',
        home_assistant_token_configured: true,
        entity_ids: ['light.ceiling', 'switch.led_strip'],
    }

    it('is disabled when lighting is off', () => {
        expect(lightingReadiness({...complete, enabled: false}).status).toBe('disabled')
    })

    it('is incomplete without url, token or entities', () => {
        expect(lightingReadiness({...complete, home_assistant_url: ''}).status).toBe('incomplete')
        expect(lightingReadiness({...complete, home_assistant_token_configured: false}).status).toBe('incomplete')
        expect(lightingReadiness({...complete, entity_ids: []}).status).toBe('incomplete')
    })

    it('accepts a freshly typed token before it is saved', () => {
        expect(lightingReadiness({
            ...complete,
            home_assistant_token_configured: false,
            home_assistant_token: 'abc',
        }).status).toBe('configured')
    })

    it('reports verified after a successful test', () => {
        expect(lightingReadiness(complete, true)).toEqual({
            status: 'verified',
            detail: 'Home Assistant · 2 entities',
        })
    })
})

describe('useRoomLighting', () => {
    it('loads config without exposing a token value', () => {
        const {lighting} = setup()

        lighting.load({lighting: {enabled: true, home_assistant_token_configured: true, entity_ids: ['light.a']}})

        expect(lighting.lighting.value.home_assistant_token).toBe('')
        expect(lighting.lighting.value.on_playback_start).toBe('turn_off')
        expect(lighting.lighting.value.entity_ids).toEqual(['light.a'])
    })

    it('toggles entity selection', () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: []}})

        lighting.toggleEntity('light.ceiling')
        lighting.toggleEntity('switch.led_strip')
        lighting.toggleEntity('light.ceiling')

        expect(lighting.lighting.value.entity_ids).toEqual(['switch.led_strip'])
    })

    it('lists stored entities that Home Assistant did not report', async () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: ['light.renamed']}})
        api.getLightingEntities.mockResolvedValueOnce({
            entities: [{entity_id: 'light.ceiling', name: 'Techo', state: 'on'}],
        })

        await lighting.detectEntities()

        expect(lighting.entityOptions.value.map((entity) => entity.entity_id))
            .toEqual(['light.ceiling', 'light.renamed'])
    })

    it('filters entities by name or id', async () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: []}})
        api.getLightingEntities.mockResolvedValueOnce({
            entities: [
                {entity_id: 'light.ceiling', name: 'Techo', state: 'on'},
                {entity_id: 'switch.led_strip', name: 'Tira LED', state: 'off'},
            ],
        })
        await lighting.detectEntities()

        lighting.entityFilter.value = 'tira'

        expect(lighting.entityOptions.value.map((entity) => entity.entity_id)).toEqual(['switch.led_strip'])
    })

    it('marks the card tested after a successful connection test', async () => {
        const {lighting, onReadinessChange} = setup()
        lighting.load({lighting: {
            enabled: true,
            home_assistant_url: 'http://ha.local:8123',
            entity_ids: ['light.ceiling'],
        }})
        lighting.lighting.value.home_assistant_token = 'abc'
        api.testLightingConnection.mockResolvedValueOnce({
            lighting: {
                enabled: true,
                home_assistant_url: 'http://ha.local:8123',
                home_assistant_token_configured: true,
                entity_ids: ['light.ceiling'],
            },
        })

        await lighting.testConnection()

        expect(api.testLightingConnection.mock.calls[0][0].lighting.home_assistant_token).toBe('abc')
        expect(lighting.lighting.value.home_assistant_token).toBe('')
        expect(lighting.state.value).toBe('tested')
        expect(onReadinessChange).toHaveBeenLastCalledWith(expect.objectContaining({status: 'verified'}))
    })

    it('saves through the lighting section', async () => {
        const {lighting, saveConfigSection} = setup()
        lighting.load({lighting: {enabled: true, entity_ids: ['light.ceiling']}})

        await lighting.save()

        expect(saveConfigSection).toHaveBeenCalledWith('lighting', expect.objectContaining({
            enabled: true,
            entity_ids: ['light.ceiling'],
        }))
        expect(saveConfigSection.mock.calls[0][1]).not.toHaveProperty('home_assistant_token')
        expect(lighting.lighting.value.home_assistant_token_configured).toBe(true)
    })

    it('calls turn on / turn off', async () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: ['light.ceiling']}})
        api.lightingTurnOn.mockResolvedValueOnce({status: 'success'})
        api.lightingTurnOff.mockResolvedValueOnce({status: 'success'})

        await lighting.switchLights('turn_on')
        await lighting.switchLights('turn_off')

        expect(api.lightingTurnOn).toHaveBeenCalledTimes(1)
        expect(api.lightingTurnOff).toHaveBeenCalledTimes(1)
        expect(lighting.switchLoading.value).toBe('')
    })
})

describe('useRoomLighting test state', () => {
    it('keeps the tested state when lights are picked after a successful test', async () => {
        const {nextTick} = await import('vue')
        const {lighting} = setup()
        lighting.load({lighting: {enabled: true, home_assistant_url: 'http://ha.local:8123', entity_ids: []}})
        api.testLightingConnection.mockResolvedValueOnce({
            lighting: {enabled: true, home_assistant_url: 'http://ha.local:8123', home_assistant_token_configured: true, entity_ids: []},
        })
        await lighting.testConnection()

        lighting.toggleEntity('light.ceiling')
        await nextTick()
        expect(lighting.tested.value).toBe(true)

        lighting.lighting.value.home_assistant_url = 'http://other:8123'
        await nextTick()
        expect(lighting.tested.value).toBe(false)
    })
})
