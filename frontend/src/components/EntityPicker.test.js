import {mount} from '@vue/test-utils'
import {describe, expect, it} from 'vitest'
import EntityPicker from './EntityPicker.vue'

const SWITCHES = [
    {entity_id: 'switch.nas11', name: 'nas11', state: 'off'},
    {entity_id: 'switch.nas21', name: 'nas21', state: 'on'},
    {entity_id: 'switch.garage', name: 'garage puerta switch', state: 'on'},
]

function single(props = {}) {
    return mount(EntityPicker, {
        props: {entities: SWITCHES, modelValue: '', multiple: false, noneLabel: 'Ninguno', ...props},
    })
}

describe('EntityPicker (single selection)', () => {
    it('lists every entity with its name, id and state, plus a none option', () => {
        const wrapper = single()

        const items = wrapper.findAll('.entity-picker-item')
        expect(items).toHaveLength(4)
        expect(items[0].text()).toBe('Ninguno')
        expect(items[1].text()).toContain('nas11')
        expect(items[1].text()).toContain('switch.nas11')
        expect(items[1].find('.entity-picker-state').text()).toBe('off')
        expect(wrapper.findAll('input[type=radio]')).toHaveLength(4)
    })

    it('emits the chosen entity id', async () => {
        const wrapper = single()

        await wrapper.findAll('input[type=radio]')[1].trigger('change')

        expect(wrapper.emitted('update:modelValue')[0]).toEqual(['switch.nas11'])
    })

    it('emits an empty id when none is chosen', async () => {
        const wrapper = single({modelValue: 'switch.nas11'})

        await wrapper.findAll('input[type=radio]')[0].trigger('change')

        expect(wrapper.emitted('update:modelValue')[0]).toEqual([''])
    })

    it('checks the stored entity, even one Home Assistant did not report', () => {
        const wrapper = single({modelValue: 'switch.renamed'})

        const checked = wrapper.findAll('input[type=radio]').filter((input) => input.element.checked)
        expect(checked).toHaveLength(1)
        expect(wrapper.text()).toContain('switch.renamed')
    })

    it('filters by name or entity id once the list is long', async () => {
        const wrapper = single({filterThreshold: 2})

        await wrapper.find('input[type=search]').setValue('nas')

        const ids = wrapper.findAll('.entity-picker-id').map((node) => node.text())
        expect(ids).toEqual(['switch.nas11', 'switch.nas21'])
    })

    it('hides the filter for short lists', () => {
        expect(single().find('input[type=search]').exists()).toBe(false)
    })

    it('shows the empty text when nothing could be loaded', () => {
        const wrapper = single({entities: [], emptyText: 'No switches'})

        expect(wrapper.text()).toContain('No switches')
    })
})

describe('EntityPicker (multiple selection)', () => {
    it('toggles entity ids in the selected array', async () => {
        const wrapper = mount(EntityPicker, {
            props: {entities: SWITCHES, modelValue: ['switch.nas21']},
        })

        await wrapper.findAll('input[type=checkbox]')[0].trigger('change')
        await wrapper.findAll('input[type=checkbox]')[1].trigger('change')

        expect(wrapper.emitted('update:modelValue')).toEqual([
            [['switch.nas21', 'switch.nas11']],
            [[]],
        ])
    })
})
