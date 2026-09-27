import {nextTick} from 'vue'
import {describe, expect, it, vi} from 'vitest'
import {useMediaPathWorkflow} from './useMediaPathWorkflow.js'

function workflow(overrides = {}) {
    return useMediaPathWorkflow({
        api: {
            previewPath: vi.fn(),
            getPathMappingSuggestions: vi.fn(),
            testPath: vi.fn(),
            navigatePath: vi.fn(),
        },
        defaultProtocol: () => 'nfs',
        isLibraryIntercepted: () => true,
        persistRouteMappings: vi.fn(),
        persistNetworkAccess: vi.fn(),
        clearSmbCredentials: vi.fn(),
        ...overrides,
    })
}

describe('useMediaPathWorkflow', () => {
    it('keeps verified route state separate from intercepted-library state', async () => {
        const subject = workflow({
            isLibraryIntercepted: () => false,
        })

        subject.initialize(
            {
                media_servers: {
                    active: 'emby',
                    providers: {
                        emby: {
                            playback: {
                                path_mappings: [
                                    {
                                        name: 'Movies',
                                        source_path: '/volume1/Video/Movies',
                                        player_path: '/NAS/Movies',
                                        protocol: 'nfs',
                                        verified: true,
                                    },
                                ],
                            },
                        },
                    },
                },
            },
            [
                {
                    library_name: 'Movies',
                    source_path: '/volume1/Video/Movies',
                },
            ],
        )
        await nextTick()

        expect(subject.detectedRows.value[0].status).toBe('not_intercepted')
        expect(subject.detectedRows.value[0].mapping.verified).toBe(true)
    })

    it('invalidates CIFS mappings without invalidating verified NFS mappings', async () => {
        const persistNetworkAccess = vi.fn(async ({pathMappings}) => ({
            media_servers: {
                active: 'emby',
                providers: {emby: {playback: {path_mappings: pathMappings}}},
            },
        }))
        const subject = workflow({persistNetworkAccess})

        subject.initialize(
            {
                media_servers: {
                    active: 'emby',
                    providers: {
                        emby: {
                            playback: {
                                path_mappings: [
                                    {
                                        name: 'Movies',
                                        source_path: '/volume1/Video/Movies',
                                        player_path: '/NAS-NFS/Movies',
                                        protocol: 'nfs',
                                        verified: true,
                                    },
                                    {
                                        name: 'Trailers',
                                        source_path: '/volume1/Video/Trailers',
                                        player_path: '/NAS-SMB/Trailers',
                                        protocol: 'cifs',
                                        verified: true,
                                    },
                                ],
                            },
                        },
                    },
                },
            },
            [],
        )

        await subject.saveNetworkAccess({
            smbAccessChanged: true,
            preMountSmb: true,
            username: 'nas',
            password: 'secret',
        })

        expect(subject.manualRows.value[0].mapping.verified).toBe(true)
        expect(subject.manualRows.value[1].mapping.verified).toBe(false)
    })
})

describe('useMediaPathWorkflow media source power switch', () => {
    const config = {
        media_servers: {
            active: 'emby',
            providers: {
                emby: {
                    playback: {
                        path_mappings: [{
                            name: 'series actuales',
                            source_path: '\\\\nas11.miesfera.net\\libreria\\libreria\\series',
                            player_path: '/nas11.miesfera.net/libreria/libreria/series',
                            protocol: 'nfs',
                            verified: true,
                            power_switch_entity_id: 'switch.nas11',
                        }],
                    },
                },
            },
        },
    }
    const library = {library_name: 'series actuales', source_path: '\\\\nas11.miesfera.net\\libreria\\libreria\\series'}

    function openRow(overrides = {}) {
        const api = {
            previewPath: vi.fn(),
            getPathMappingSuggestions: vi.fn(),
            testPath: vi.fn().mockResolvedValue({}),
            navigatePath: vi.fn(),
            powerOnPath: vi.fn().mockResolvedValue({status: 'ok'}),
        }
        const persistRouteMappings = vi.fn(async (mappings) => ({
            media_servers: {active: 'emby', providers: {emby: {playback: {path_mappings: mappings}}}},
        }))
        const subject = workflow({api, persistRouteMappings, ...overrides})
        subject.initialize(config, [library])
        subject.selectRow(subject.detectedRows.value[0])
        return {subject, api, persistRouteMappings}
    }

    it('loads the stored switch into the editor', () => {
        const {subject} = openRow()

        expect(subject.form.value.power_switch_entity_id).toBe('switch.nas11')
    })

    it('changing only the switch keeps the path verified', async () => {
        const {subject, persistRouteMappings} = openRow()

        subject.form.value.power_switch_entity_id = 'switch.nas21'
        await subject.savePath(false)

        expect(subject.formDirty.value).toBe(false)
        const saved = persistRouteMappings.mock.calls[0][0][0]
        expect(saved.power_switch_entity_id).toBe('switch.nas21')
        expect(saved.verified).toBe(true)
    })

    it('sends the switch with the path test so the backend can wake the NAS', async () => {
        const {subject, api} = openRow()

        await subject.testPath()

        expect(api.testPath.mock.calls[0][0].power_switch_entity_id).toBe('switch.nas11')
    })

    it('powers on the NAS behind the edited path', async () => {
        const {subject, api} = openRow()

        await subject.powerOnSource()

        expect(api.powerOnPath).toHaveBeenCalledWith({
            player_path: '/nas11.miesfera.net/libreria/libreria/series',
            protocol: 'nfs',
            power_switch_entity_id: 'switch.nas11',
            power_wait_timeout_seconds: null,
        })
        expect(subject.powerOnLoading.value).toBe(false)
    })
})

describe('useMediaPathWorkflow NAS boot timeout', () => {
    function openRow(mapping) {
        const api = {
            previewPath: vi.fn(),
            getPathMappingSuggestions: vi.fn(),
            testPath: vi.fn().mockResolvedValue({}),
            navigatePath: vi.fn(),
            powerOnPath: vi.fn().mockResolvedValue({status: 'ok'}),
        }
        const persistRouteMappings = vi.fn(async (mappings) => ({
            media_servers: {active: 'emby', providers: {emby: {playback: {path_mappings: mappings}}}},
        }))
        const subject = workflow({api, persistRouteMappings})
        subject.initialize(
            {media_servers: {active: 'emby', providers: {emby: {playback: {path_mappings: [mapping]}}}}},
            [{library_name: 'Peliculas', source_path: mapping.source_path}],
        )
        subject.selectRow(subject.detectedRows.value[0])
        return {subject, api, persistRouteMappings}
    }

    const base = {
        name: 'Peliculas',
        source_path: '\\\\nas11\\libreria',
        player_path: '/172.16.10.211/libreria',
        protocol: 'nfs',
        verified: true,
        power_switch_entity_id: 'switch.nas11',
    }

    it('loads and saves the stored timeout', async () => {
        const {subject, persistRouteMappings} = openRow({...base, power_wait_timeout_seconds: 120})

        expect(subject.form.value.power_wait_timeout_seconds).toBe(120)
        subject.form.value.power_wait_timeout_seconds = 240
        await subject.savePath(false)

        expect(persistRouteMappings.mock.calls[0][0][0].power_wait_timeout_seconds).toBe(240)
        expect(persistRouteMappings.mock.calls[0][0][0].verified).toBe(true)
    })

    it('sends null for an empty timeout so the default applies', async () => {
        const {subject, api, persistRouteMappings} = openRow(base)

        subject.form.value.power_wait_timeout_seconds = ''
        await subject.powerOnSource()
        await subject.savePath(false)

        expect(api.powerOnPath.mock.calls[0][0].power_wait_timeout_seconds).toBeNull()
        expect(persistRouteMappings.mock.calls[0][0][0].power_wait_timeout_seconds).toBeNull()
    })

    it('sends the timeout with the path test', async () => {
        const {subject, api} = openRow({...base, power_wait_timeout_seconds: 90})

        await subject.testPath()

        expect(api.testPath.mock.calls[0][0].power_wait_timeout_seconds).toBe(90)
    })
})
