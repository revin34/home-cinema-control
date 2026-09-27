import {describe, expect, it, vi} from 'vitest'
import {nextTick} from 'vue'

vi.mock('../api/index.js', () => ({
    api: {
        getHomeAssistantEntities: vi.fn(),
        lightingTurnOn: vi.fn(),
        lightingTurnOff: vi.fn(),
    },
}))

const {api} = await import('../api/index.js')
const {lightingReadiness, useRoomLighting} = await import('./useRoomLighting.js')

function setup({homeAssistantReady = true} = {}) {
    const configWithSection = vi.fn(async (section, value) => ({[section]: value}))
    const saveConfigSection = vi.fn(async (section, value) => ({[section]: {...value}}))
    const onReadinessChange = vi.fn()
    const lighting = useRoomLighting({
        configWithSection,
        saveConfigSection,
        homeAssistantReady: () => homeAssistantReady,
        onReadinessChange,
    })
    return {lighting, configWithSection, saveConfigSection, onReadinessChange}
}

describe('lightingReadiness', () => {
    const complete = {enabled: true, entity_ids: ['light.ceiling', 'switch.led_strip']}

    it('is disabled when lighting is off', () => {
        expect(lightingReadiness({...complete, enabled: false}).status).toBe('disabled')
    })

    it('needs Home Assistant and at least one entity', () => {
        expect(lightingReadiness(complete, false).status).toBe('incomplete')
        expect(lightingReadiness({...complete, entity_ids: []}).status).toBe('incomplete')
    })

    it('is configured with Home Assistant and entities', () => {
        expect(lightingReadiness(complete)).toEqual({
            status: 'configured',
            detail: 'Home Assistant · 2 entities',
        })
    })
})

describe('useRoomLighting', () => {
    it('loads config with defaults', () => {
        const {lighting} = setup()

        lighting.load({lighting: {enabled: true, entity_ids: ['light.a']}})

        expect(lighting.lighting.value.on_playback_start).toBe('turn_off')
        expect(lighting.lighting.value.fade_out_seconds).toBe(0)
        expect(lighting.lighting.value.fade_in_seconds).toBe(0)
        expect(lighting.lighting.value.entity_ids).toEqual(['light.a'])
    })

    it('reports incomplete while Home Assistant is not configured', () => {
        const {lighting} = setup({homeAssistantReady: false})
        lighting.load({lighting: {enabled: true, entity_ids: ['light.a']}})

        expect(lighting.state.value).toBe('incomplete')
    })

    it('toggles entity selection and reports readiness', async () => {
        const {lighting, onReadinessChange} = setup()
        lighting.load({lighting: {enabled: true, entity_ids: []}})

        lighting.toggleEntity('light.ceiling')
        lighting.toggleEntity('switch.led_strip')
        lighting.toggleEntity('light.ceiling')
        await nextTick()

        expect(lighting.lighting.value.entity_ids).toEqual(['switch.led_strip'])
        expect(onReadinessChange).toHaveBeenLastCalledWith(expect.objectContaining({status: 'configured'}))
    })

    it('detects light and switch entities through Home Assistant', async () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: ['light.renamed']}})
        api.getHomeAssistantEntities.mockResolvedValueOnce({
            entities: [{entity_id: 'light.ceiling', name: 'Techo', state: 'on'}],
        })

        await lighting.detectEntities()

        expect(api.getHomeAssistantEntities.mock.calls.at(-1)[1]).toEqual(['light', 'switch'])
        expect(lighting.entityOptions.value.map((entity) => entity.entity_id))
            .toEqual(['light.ceiling', 'light.renamed'])
    })

    it('filters entities by name or id', async () => {
        const {lighting} = setup()
        lighting.load({lighting: {entity_ids: []}})
        api.getHomeAssistantEntities.mockResolvedValueOnce({
            entities: [
                {entity_id: 'light.ceiling', name: 'Techo', state: 'on'},
                {entity_id: 'switch.led_strip', name: 'Tira LED', state: 'off'},
            ],
        })
        await lighting.detectEntities()

        lighting.entityFilter.value = 'tira'

        expect(lighting.entityOptions.value.map((entity) => entity.entity_id)).toEqual(['switch.led_strip'])
    })

    it('saves through the lighting section', async () => {
        const {lighting, saveConfigSection} = setup()
        lighting.load({lighting: {enabled: true, entity_ids: ['light.ceiling'], fade_out_seconds: 4}})

        await lighting.save()

        expect(saveConfigSection).toHaveBeenCalledWith('lighting', expect.objectContaining({
            enabled: true,
            entity_ids: ['light.ceiling'],
            fade_out_seconds: 4,
        }))
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
