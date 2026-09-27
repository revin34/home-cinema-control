<template>
  <div class="view-content view-ambient sala-view">
    <div :style="{ backgroundImage: `url(${heroBg})` }" class="ambient-bg"></div>
    <div :style="{ backgroundImage: `url(${heroBg})` }" class="sala-scene-bg"></div>

    <div class="view-body sala-view-body">
      <section class="sala-showcase">
        <h1 class="sala-showcase-title">{{ $t('x-sala-title') }}</h1>
        <p class="sala-showcase-subtitle">{{ $t('x-sala-subtitle') }} {{ $t('x-sala-summary-title') }}</p>
        <div class="sala-showcase-actions">
          <HelpTooltip v-if="arpAvailable" :text="$t('x-network-tooltip-scan')">
            <IconActionButton
                :label="$t('x-network-scan')"
                :loading="scanning"
                :loading-label="$t('x-network-scanning')"
                icon="network"
                @click="scan"
            />
          </HelpTooltip>
          <span v-if="devices.length" class="caption">
            {{ devices.length }} {{ $t('x-network-scan-found') }}
          </span>
        </div>
      </section>

      <div v-if="loading" class="text-sm" style="color:var(--text-muted)">{{ $t('x-common-loading') }}</div>

      <template v-else>
        <div class="sala-kicker">
          <span class="s-dot dim"></span>
          <span>{{ $t('x-nav-config-section') }}</span>
        </div>
        <div class="sala-shell">
        <div class="sala-grid">
          <!-- TV section -->
          <section :class="roomAccentClass(tvState)" class="panel room-device-card">
            <div class="panel-head room-card-head">
              <div>
                <h2 class="panel-title label-with-help">
                  <Tv :size="13" :stroke-width="2.3"/>
                  {{ $t('x-tv-title') }}
                  <HelpTooltip :text="$t('x-tv-tooltip-section')"/>
                </h2>
                <p class="room-card-sub">{{ $t('x-tv-card-subtitle') }}</p>
              </div>
              <div class="room-card-controls">
                <span :class="['room-state', roomStateClass(tvState)]">{{ roomStateLabel(tvState) }}</span>
                <button
                    :aria-label="$t('x-tv-title')"
                    :aria-pressed="tv.enabled"
                    :class="['toggle-switch', tv.enabled && 'on']"
                    @click="tv.enabled = !tv.enabled"
                >
                  <div class="toggle-thumb"></div>
                </button>
              </div>
            </div>
            <div v-if="tv.enabled" class="panel-body">
              <div class="form-label label-with-help">
                <label for="tv-model">{{ $t('x-tv-model') }}</label>
                <HelpTooltip :text="$t('x-tv-tooltip-model')"/>
              </div>
              <FormSelect
                  id="tv-model"
                  v-model="tv.model"
                  :options="tvModels.map(m => ({ value: m, label: m }))"
                  class="mb-4"
                  @change="onTvModelChange"
              />

                <template v-if="tv.model === 'LG'">
                  <label class="form-label" for="tv-ip">{{ $t('x-tv-ip') }}</label>
                  <IpInput id="tv-ip" v-model="tv.ip" :devices="devices" class="mb-4"/>

                  <button :disabled="tvTestLoading" class="btn-ghost mb-4" @click="testTvConnection">
                    {{ tvTestLoading ? $t('x-common-testing') : $t('x-tv-test-connection') }}
                  </button>

                  <label class="form-label" for="tv-mac">{{ $t('x-tv-mac') }}</label>
                  <input id="tv-mac" v-model="tv.mac" :disabled="arpAvailable" class="form-input mb-1" type="text"/>
                  <p class="section-hint">{{ tv.mac ? $t('x-tv-mac-detected') : $t('x-tv-mac-pending') }}</p>
                  <p v-if="!arpAvailable" class="section-hint" style="color:var(--status-warning)">
                    {{ $t('x-tv-mac-linux-only') }}</p>

                  <div class="form-label label-with-help">
                    <label for="tv-hdmi-input">{{ $t('x-tv-hdmi-input') }}</label>
                    <HelpTooltip :text="$t('x-tv-tooltip-hdmi-input')"/>
                  </div>
                  <FormSelect
                      id="tv-hdmi-input"
                      v-model="selectedTvSourceIndex"
                      :disabled="!tvTested"
                      :options="tv.available_hdmi_inputs.map((src, i) => ({ value: i, label: src.nombre || src.name || src.id }))"
                      class="mb-3"
                  />
                  <p v-if="!tvTested" class="section-hint">{{ $t('x-tv-actions-locked-hint') }}</p>

                  <div class="icon-action-row">
                    <HelpTooltip
                        :text="tvTested ? $t('x-tv-action-detect-inputs-tooltip') : $t('x-tv-actions-locked-tooltip')">
                      <IconActionButton
                          :disabled="!tvTested"
                          :label="$t('x-tv-action-detect-inputs')"
                          :loading="tvSourcesLoading"
                          :loading-label="$t('x-tv-detecting-inputs')"
                          icon="scan"
                          @click="getTvSources"
                      />
                    </HelpTooltip>
                    <HelpTooltip
                        :text="tvTested ? $t('x-tv-action-switch-player-tooltip') : $t('x-tv-actions-locked-tooltip')">
                      <IconActionButton
                          :disabled="!tvTested"
                          :label="$t('x-tv-action-switch-player')"
                          icon="player"
                          @click="tvSwitchInput"
                      />
                    </HelpTooltip>
                    <HelpTooltip
                        :text="!tvTested
                          ? $t('x-tv-actions-locked-tooltip')
                          : mediaServerConfigured
                            ? $t('x-tv-action-restore-media-server-tooltip', {server: mediaServerBrand.label})
                            : $t('x-tv-action-restore-media-server-not-configured-tooltip')">
                      <IconActionButton
                          :brand="mediaServerBrand.brand"
                          :disabled="!tvTested || !mediaServerConfigured"
                          :label="$t('x-tv-action-restore-media-server', {server: mediaServerBrand.label})"
                          icon="server"
                          @click="tvRestoreInput"
                      />
                    </HelpTooltip>
                  </div>
                </template>

              <template v-if="tv.model === 'SONY'">
                <p class="section-hint mb-4">{{ $t('x-tv-sony-hint') }}</p>

                <label class="form-label" for="tv-ip-sony">{{ $t('x-tv-ip') }}</label>
                <IpInput id="tv-ip-sony" v-model="tv.ip" :devices="devices" class="mb-4"/>

                <div class="form-label label-with-help">
                  <label for="tv-psk-sony">{{ $t('x-tv-sony-psk') }}</label>
                  <HelpTooltip :text="$t('x-tv-tooltip-sony-psk')"/>
                </div>
                <input id="tv-psk-sony" v-model="tv.sony_psk" autocomplete="off"
                       class="form-input mb-1" type="password"/>
                <p v-if="tv.sony_psk_configured" class="section-hint mb-4">
                  {{ $t('x-tv-sony-psk-configured') }}
                </p>

                <button :disabled="tvTestLoading" class="btn-ghost mb-4" @click="testTvConnection">
                  {{ tvTestLoading ? $t('x-common-testing') : $t('x-tv-test-connection') }}
                </button>

                <label class="form-label" for="tv-mac-sony">{{ $t('x-tv-mac') }}</label>
                <input id="tv-mac-sony" v-model="tv.mac" :disabled="arpAvailable" class="form-input mb-1" type="text"/>
                <p class="section-hint">{{ tv.mac ? $t('x-tv-mac-detected') : $t('x-tv-mac-pending') }}</p>
                <p v-if="!arpAvailable" class="section-hint" style="color:var(--status-warning)">
                  {{ $t('x-tv-mac-linux-only') }}</p>

                <div class="form-label label-with-help">
                  <label for="tv-hdmi-input-sony">{{ $t('x-tv-hdmi-input') }}</label>
                  <HelpTooltip :text="$t('x-tv-tooltip-hdmi-input')"/>
                </div>
                <FormSelect
                    id="tv-hdmi-input-sony"
                    v-model="selectedTvSourceIndex"
                    :disabled="!tvTested"
                    :options="tv.available_hdmi_inputs.map((src, i) => ({ value: i, label: src.nombre || src.name || src.id }))"
                    class="mb-3"
                />
                <p v-if="!tvTested" class="section-hint">{{ $t('x-tv-actions-locked-hint') }}</p>

                <div class="icon-action-row">
                  <HelpTooltip
                      :text="tvTested ? $t('x-tv-action-detect-inputs-tooltip') : $t('x-tv-actions-locked-tooltip')">
                    <IconActionButton
                        :disabled="!tvTested"
                        :label="$t('x-tv-action-detect-inputs')"
                        :loading="tvSourcesLoading"
                        :loading-label="$t('x-tv-detecting-inputs')"
                        icon="scan"
                        @click="getTvSources"
                    />
                  </HelpTooltip>
                  <HelpTooltip
                      :text="tvTested ? $t('x-tv-action-switch-player-tooltip') : $t('x-tv-actions-locked-tooltip')">
                    <IconActionButton
                        :disabled="!tvTested"
                        :label="$t('x-tv-action-switch-player')"
                        icon="player"
                        @click="tvSwitchInput"
                    />
                  </HelpTooltip>
                </div>

                <div class="form-label label-with-help mt-4">
                  <label for="tv-app-uri-sony">{{ $t('x-tv-sony-app-uri') }}</label>
                  <HelpTooltip :text="$t('x-tv-sony-app-uri-tooltip')"/>
                </div>
                <FormSelect
                    id="tv-app-uri-sony"
                    v-model="selectedSonyAppUri"
                    :disabled="!tvTested || !mediaServerConfigured"
                    :options="sonyAvailableAppOptions"
                    class="mb-3"
                />

                <div class="icon-action-row">
                  <HelpTooltip
                      :text="tvTested ? $t('x-tv-action-detect-apps-tooltip') : $t('x-tv-actions-locked-tooltip')">
                    <IconActionButton
                        :disabled="!tvTested || !mediaServerConfigured"
                        :label="$t('x-tv-action-detect-apps')"
                        :loading="tvAppsLoading"
                        :loading-label="$t('x-tv-detecting-apps')"
                        icon="scan"
                        @click="getTvApps"
                      />
                  </HelpTooltip>
                  <HelpTooltip
                      :text="!tvTested
                          ? $t('x-tv-actions-locked-tooltip')
                          : !mediaServerConfigured
                            ? $t('x-tv-action-restore-media-server-not-configured-tooltip')
                            : $t('x-tv-action-restore-media-server-tooltip', {server: mediaServerBrand.label})">
                    <IconActionButton
                        :brand="mediaServerBrand.brand"
                        :disabled="!tvTested || !mediaServerConfigured || !sonyAppMapped"
                        :label="$t('x-tv-action-restore-media-server', {server: mediaServerBrand.label})"
                        icon="server"
                        @click="tvRestoreInput"
                    />
                    </HelpTooltip>
                  </div>
                <p v-if="tvTested && sonyAppsDetected && !sonyAppMapped" class="section-hint"
                   style="color:var(--status-warning)">
                  {{ $t('x-tv-sony-app-not-found', {server: mediaServerBrand.label}) }}
                </p>
                </template>

                <template v-if="tv.model === 'SCRIPTS'">
                  <label class="form-label" for="tv-startup-script">{{ $t('x-tv-startup-script') }}</label>
                  <input id="tv-startup-script" v-model="tv.startup_script" class="form-input mb-3" type="text"/>
                  <button class="btn-ghost mb-4" @click="tvSwitchInput">{{ $t('x-tv-test-startup-script') }}</button>

                  <label class="form-label" for="tv-shutdown-script">{{ $t('x-tv-shutdown-script') }}</label>
                  <input id="tv-shutdown-script" v-model="tv.shutdown_script" class="form-input mb-3" type="text"/>
                  <button class="btn-ghost mb-2" @click="tvRestoreInput">{{ $t('x-tv-test-shutdown-script') }}</button>
                </template>

              <div class="room-card-actions">
                <button class="btn-ghost" @click="saveTv">{{ $t('x-tv-save') }}</button>
              </div>
            </div>
            <div v-else class="panel-body room-disabled-body">
              <p>{{ $t('x-tv-disabled-copy') }}</p>
              <button class="btn-ghost" @click="saveTv">{{ $t('x-tv-save') }}</button>
            </div>
          </section>

          <!-- AV section -->
          <section :class="roomAccentClass(avState)" class="panel room-device-card">
            <div class="panel-head room-card-head">
              <div>
                <h2 class="panel-title label-with-help">
                  <Speaker :size="13" :stroke-width="2.3"/>
                  {{ $t('x-av-title') }}
                  <HelpTooltip :text="$t('x-av-tooltip-section')"/>
                </h2>
                <p class="room-card-sub">{{ $t('x-av-card-subtitle') }}</p>
              </div>
              <div class="room-card-controls">
                <span :class="['room-state', roomStateClass(avState)]">{{ roomStateLabel(avState) }}</span>
                <button
                    :aria-label="$t('x-av-title')"
                    :aria-pressed="av.enabled"
                    :class="['toggle-switch', av.enabled && 'on']"
                    @click="av.enabled = !av.enabled"
                >
                  <div class="toggle-thumb"></div>
                </button>
              </div>
            </div>
            <div v-if="av.enabled" class="panel-body">
              <div class="form-label label-with-help">
                <label for="av-model">{{ $t('x-av-model') }}</label>
                <HelpTooltip :text="$t('x-av-tooltip-model')"/>
              </div>
              <FormSelect
                  id="av-model"
                  v-model="av.model"
                  :options="avModels.map(m => ({ value: m, label: m }))"
                  class="mb-4"
                  @change="onAvModelChange"
              />

              <div class="form-label label-with-help">
                <label for="av-hdmi-delay">{{ $t('x-av-hdmi-delay') }}</label>
                <HelpTooltip :text="$t('x-av-tooltip-hdmi-delay')"/>
              </div>
              <input id="av-hdmi-delay" v-model.number="av.hdmi_switch_delay_seconds" class="form-input mb-3" step="0.5"
                     type="number"/>

              <div class="flex items-center gap-2 mb-4">
                <label class="flex items-center gap-2" style="cursor:pointer">
                  <input v-model="av.always_on" type="checkbox"/>
                  <span class="body-text">{{ $t('x-av-always-on') }}</span>
                </label>
                <HelpTooltip :text="$t('x-av-tooltip-always-on')"/>
              </div>

                <template v-if="av.model !== 'SCRIPTS'">
                  <label class="form-label" for="av-ip">{{ $t('x-av-ip') }}</label>
                  <IpInput id="av-ip" v-model="av.ip" :devices="devices" class="mb-4"/>

                  <template v-if="av.model === 'TRINNOV'">
                    <div class="form-label label-with-help">
                      <label for="av-mac">{{ $t('x-av-trinnov-mac') }}</label>
                      <HelpTooltip :text="$t('x-av-tooltip-trinnov-mac')"/>
                    </div>
                    <input id="av-mac" v-model="av.trinnov_mac" :disabled="trinnovMacFieldLocked"
                           class="form-input mb-1" type="text"/>
                    <p class="section-hint">
                      {{ av.trinnov_mac ? $t('x-av-trinnov-mac-detected') : $t('x-av-trinnov-mac-pending') }}
                    </p>
                    <p v-if="!arpAvailable" class="section-hint" style="color:var(--status-warning)">
                      {{ $t('x-av-trinnov-mac-manual') }}
                    </p>
                    <div class="icon-action-row mb-4">
                      <HelpTooltip :text="$t('x-av-action-detect-trinnov-mac-tooltip')">
                        <IconActionButton
                            :label="$t('x-av-action-detect-trinnov-mac')"
                            :loading="scanning"
                            :loading-label="$t('x-network-scanning')"
                            icon="network"
                            @click="detectTrinnovMac"
                        />
                      </HelpTooltip>
                    </div>
                    <p class="hint-copy mb-4">{{ $t('x-av-trinnov-hint') }}</p>
                  </template>

                  <div class="icon-action-row mb-4">
                    <HelpTooltip :text="$t('x-av-action-power-on-tooltip')">
                      <IconActionButton
                          :disabled="avPowerActionsLocked"
                          :label="$t('x-av-action-power-on')"
                          :loading="avPowerOnLoading"
                          :loading-label="$t('x-common-testing')"
                          icon="powerOn"
                          @click="testAvPowerOn"
                      />
                    </HelpTooltip>
                    <HelpTooltip :text="$t('x-av-action-power-off-tooltip')">
                      <IconActionButton
                          :disabled="avPowerActionsLocked"
                          :label="$t('x-av-action-power-off')"
                          :loading="avPowerOffLoading"
                          :loading-label="$t('x-common-testing')"
                          icon="powerOff"
                          @click="testAvPowerOff"
                      />
                    </HelpTooltip>
                  </div>
                  <p v-if="avPowerActionsLocked" class="section-hint mb-4">
                    {{ $t('x-av-trinnov-power-locked') }}
                  </p>

                  <div class="form-label label-with-help">
                    <label for="av-hdmi-input">{{
                        av.model === 'TRINNOV' ? $t('x-av-trinnov-source-profile') : $t('x-av-hdmi-input')
                      }}</label>
                    <HelpTooltip
                        :text="av.model === 'TRINNOV' ? $t('x-av-tooltip-trinnov-source-profile') : $t('x-av-tooltip-hdmi-input')"/>
                  </div>
                  <FormSelect
                      id="av-hdmi-input"
                      v-model="selectedAvSource"
                      :disabled="trinnovSourcesLocked"
                      :options="av.available_hdmi_inputs.map(src => ({ value: src.param, label: src.name }))"
                      class="mb-3"
                      @change="onAvSourceChange"
                  />
                  <p v-if="trinnovSourcesLocked" class="section-hint mb-3">
                    {{ $t('x-av-trinnov-sources-locked') }}
                  </p>

                  <div class="icon-action-row">
                    <HelpTooltip :text="$t('x-av-action-detect-inputs-tooltip')">
                      <IconActionButton
                          :label="$t('x-av-action-detect-inputs')"
                          :loading="avSourcesLoading"
                          :loading-label="$t('x-av-detecting-inputs')"
                          icon="scan"
                          @click="getAvSources"
                      />
                    </HelpTooltip>
                    <HelpTooltip :text="$t('x-av-action-test-player-input-tooltip')">
                      <IconActionButton
                          :disabled="trinnovSourcesLocked"
                          :label="$t('x-av-action-test-player-input')"
                          :loading="avHdmiLoading"
                          :loading-label="$t('x-common-testing')"
                          icon="player"
                          @click="testAvHdmi"
                      />
                    </HelpTooltip>
                  </div>
                </template>

                <template v-if="av.model === 'SCRIPTS'">
                  <label class="form-label" for="av-power-on-script">{{ $t('x-av-power-on-script') }}</label>
                  <input id="av-power-on-script" v-model="av.power_on_command" class="form-input mb-3" type="text"/>
                  <button class="btn-ghost mb-4" @click="testAvPowerOn">{{ $t('x-av-test-power-on') }}</button>

                  <label class="form-label" for="av-hdmi-script">{{ $t('x-av-hdmi-script') }}</label>
                  <input id="av-hdmi-script" v-model="av.hdmi_input_command" class="form-input mb-3" type="text"/>
                  <button class="btn-ghost mb-4" @click="testAvHdmi">{{ $t('x-av-test-hdmi-switch') }}</button>

                  <label class="form-label" for="av-power-off-script">{{ $t('x-av-power-off-script') }}</label>
                  <input id="av-power-off-script" v-model="av.power_off_command" class="form-input mb-3" type="text"/>
                  <button class="btn-ghost mb-2" @click="testAvPowerOff">{{ $t('x-av-test-power-off') }}</button>
                </template>

              <div class="room-card-actions">
                <button class="btn-ghost" @click="saveAv">{{ $t('x-av-save') }}</button>
              </div>
            </div>
            <div v-else class="panel-body room-disabled-body">
              <p>{{ $t('x-av-disabled-copy') }}</p>
              <button class="btn-ghost" @click="saveAv">{{ $t('x-av-save') }}</button>
            </div>
          </section>

          <aside class="room-help-column">
            <div class="room-help-card">
              <p class="room-help-title">
                <Info :size="13" :stroke-width="2.3"/>
                {{ $t('x-sala-help-title') }}
              </p>
              <ol class="room-help-list">
                <li>{{ $t('x-sala-help-step-tv') }}</li>
                <li>{{ $t('x-sala-help-step-av') }}</li>
                <li>{{ $t('x-sala-help-step-lighting') }}</li>
                <li>{{ $t('x-sala-help-step-save') }}</li>
              </ol>
            </div>
          </aside>

          <!-- Lighting section -->
          <section :class="roomAccentClass(lightingState)" class="panel room-device-card">
            <div class="panel-head room-card-head">
              <div>
                <h2 class="panel-title label-with-help">
                  <Lightbulb :size="13" :stroke-width="2.3"/>
                  {{ $t('x-lighting-title') }}
                  <HelpTooltip :text="$t('x-lighting-tooltip-section')"/>
                </h2>
                <p class="room-card-sub">{{ $t('x-lighting-card-subtitle') }}</p>
              </div>
              <div class="room-card-controls">
                <span :class="['room-state', roomStateClass(lightingState)]">{{ roomStateLabel(lightingState) }}</span>
                <button
                    :aria-label="$t('x-lighting-title')"
                    :aria-pressed="lighting.enabled"
                    :class="['toggle-switch', lighting.enabled && 'on']"
                    @click="lighting.enabled = !lighting.enabled"
                >
                  <div class="toggle-thumb"></div>
                </button>
              </div>
            </div>
            <div v-if="lighting.enabled" class="panel-body">
              <div class="form-label label-with-help">
                <label for="lighting-ha-url">{{ $t('x-lighting-ha-url') }}</label>
                <HelpTooltip :text="$t('x-lighting-tooltip-ha-url')"/>
              </div>
              <input id="lighting-ha-url" v-model.trim="lighting.home_assistant_url" autocomplete="off"
                     class="form-input mb-3" placeholder="http://homeassistant.local:8123" type="url"/>

              <div class="form-label label-with-help">
                <label for="lighting-ha-token">{{ $t('x-lighting-ha-token') }}</label>
                <HelpTooltip :text="$t('x-lighting-tooltip-ha-token')"/>
              </div>
              <input id="lighting-ha-token" v-model="lighting.home_assistant_token" autocomplete="off"
                     class="form-input mb-1" type="password"/>
              <p v-if="lighting.home_assistant_token_configured" class="section-hint mb-4">
                {{ $t('x-lighting-ha-token-configured') }}
              </p>

              <div class="mb-4">
                <button :disabled="lightingTestLoading" class="btn-ghost" @click="testLighting">
                  {{ lightingTestLoading ? $t('x-common-testing') : $t('x-lighting-test-connection') }}
                </button>
              </div>

              <div class="form-label label-with-help">
                <span>{{ $t('x-lighting-entities') }}</span>
                <HelpTooltip :text="$t('x-lighting-tooltip-entities')"/>
              </div>
              <div class="icon-action-row mb-3">
                <IconActionButton
                    :label="$t('x-lighting-action-detect-entities')"
                    :loading="lightingEntitiesLoading"
                    :loading-label="$t('x-lighting-detecting-entities')"
                    icon="scan"
                    @click="detectLightingEntities"
                />
              </div>
              <input v-if="lightingEntities.length > 8" v-model="lightingEntityFilter"
                     :placeholder="$t('x-lighting-entities-filter')" class="form-input mb-2" type="search"/>
              <div v-if="lightingEntityOptions.length" class="lighting-entity-list mb-4">
                <label v-for="entity in lightingEntityOptions" :key="entity.entity_id" class="lighting-entity">
                  <input :aria-label="entity.name" :checked="isLightingEntitySelected(entity.entity_id)" type="checkbox"
                         @change="toggleLightingEntity(entity.entity_id)"/>
                  <span class="lighting-entity-name">{{ entity.name }}</span>
                  <span class="lighting-entity-id">{{ entity.entity_id }}</span>
                </label>
              </div>
              <p v-else class="section-hint mb-4">{{ $t('x-lighting-entities-empty') }}</p>

              <div class="form-label label-with-help">
                <label for="lighting-on-start">{{ $t('x-lighting-on-start') }}</label>
                <HelpTooltip :text="$t('x-lighting-tooltip-on-start')"/>
              </div>
              <FormSelect id="lighting-on-start" v-model="lighting.on_playback_start"
                          :options="lightingActionOptions" class="mb-3"/>

              <div class="form-label label-with-help">
                <label for="lighting-on-stop">{{ $t('x-lighting-on-stop') }}</label>
                <HelpTooltip :text="$t('x-lighting-tooltip-on-stop')"/>
              </div>
              <FormSelect id="lighting-on-stop" v-model="lighting.on_playback_stop"
                          :options="lightingActionOptions" class="mb-3"/>

              <div class="lighting-fade-grid mb-4">
                <div>
                  <div class="form-label label-with-help">
                    <label for="lighting-fade-out">{{ $t('x-lighting-fade-out') }}</label>
                    <HelpTooltip :text="$t('x-lighting-tooltip-fade-out')"/>
                  </div>
                  <input id="lighting-fade-out" v-model.number="lighting.fade_out_seconds" class="form-input"
                         inputmode="decimal" max="300" min="0" step="0.5" type="number"/>
                </div>
                <div>
                  <div class="form-label label-with-help">
                    <label for="lighting-fade-in">{{ $t('x-lighting-fade-in') }}</label>
                    <HelpTooltip :text="$t('x-lighting-tooltip-fade-in')"/>
                  </div>
                  <input id="lighting-fade-in" v-model.number="lighting.fade_in_seconds" class="form-input"
                         inputmode="decimal" max="300" min="0" step="0.5" type="number"/>
                </div>
              </div>

              <div class="icon-action-row mb-4">
                <IconActionButton
                    :disabled="!lighting.entity_ids.length"
                    :label="$t('x-lighting-action-turn-on')"
                    :loading="lightingSwitchLoading === 'turn_on'"
                    icon="power-on"
                    @click="switchLighting('turn_on')"
                />
                <IconActionButton
                    :disabled="!lighting.entity_ids.length"
                    :label="$t('x-lighting-action-turn-off')"
                    :loading="lightingSwitchLoading === 'turn_off'"
                    icon="power-off"
                    @click="switchLighting('turn_off')"
                />
              </div>

              <div class="room-card-actions">
                <button class="btn-ghost" @click="saveLighting">{{ $t('x-lighting-save') }}</button>
              </div>
            </div>
            <div v-else class="panel-body room-disabled-body">
              <p>{{ $t('x-lighting-disabled-copy') }}</p>
              <button class="btn-ghost" @click="saveLighting">{{ $t('x-lighting-save') }}</button>
            </div>
          </section>
        </div>
      </div>

      <StepNav :current-step="4"/>
    </template>
    </div>
  </div>
</template>

<script setup>
import {computed, nextTick, onMounted, ref, watch} from 'vue'
import {useI18n} from 'vue-i18n'
import {Info, Lightbulb, Speaker, Tv} from '@lucide/vue'
import {api} from '../api/index.js'
import heroBg from '../assets/backgrounds/bg-sala.png'
import {useToast} from '../composables/useToast.js'
import StepNav from '../components/StepNav.vue'
import HelpTooltip from '../components/HelpTooltip.vue'
import IpInput from '../components/IpInput.vue'
import IconActionButton from '../components/IconActionButton.vue'
import FormSelect from '../components/FormSelect.vue'
import {useNetworkScan} from '../composables/useNetworkScan.js'
import {useConfigSectionSave} from '../composables/useConfigSectionSave.js'
import {useMediaServerBrand} from '../composables/useMediaServerBrand.js'
import {useActiveMediaServer} from '../composables/useActiveMediaServer.js'
import {patchSetupReadiness} from '../composables/useSetupReadiness.js'
import {LIGHTING_ACTIONS, useRoomLighting} from '../composables/useRoomLighting.js'

const {t} = useI18n()
const toast = useToast()
const {saveSection} = useConfigSectionSave()

const loading = ref(true)
const fullConfig = ref({})
const arpAvailable = ref(true)
const {scanning, devices, scan} = useNetworkScan()

const {type: mediaServerType, provider: mediaServerProvider} = useActiveMediaServer(() => fullConfig.value)
const {brand: mediaServerBrand} = useMediaServerBrand(mediaServerType)
const mediaServerConfigured = computed(() => Boolean(mediaServerProvider.value.server_url))

/* TV state */
const tv = ref({})
const originalTv = ref({})
const originalRoomReadiness = ref({tv: null, av: null})
const tvModels = ref([])
const selectedTvSourceIndex = ref(0)
const tvTestLoading = ref(false)
const tvSourcesLoading = ref(false)
const tvAppsLoading = ref(false)
const tvTested = ref(false)

const tvState = computed(() => {
  if (!tv.value.enabled) return 'disabled'
  if (!tv.value.model) return 'incomplete'
  if (tv.value.model === 'LG' && !tv.value.ip) return 'incomplete'
  if (tv.value.model === 'SONY' && (!tv.value.ip || !tv.value.sony_psk_configured)) return 'incomplete'
  if (tv.value.model === 'SCRIPTS' && !tv.value.startup_script) return 'incomplete'
  return tvTested.value ? 'tested' : 'configured'
})

const sonyAvailableAppOptions = computed(() =>
    (tv.value.sony_available_apps || []).map((app) => ({value: app.uri, label: app.title || app.uri}))
)

const selectedSonyAppUri = computed({
  get: () => (tv.value.sony_app_uris || {})[mediaServerType.value] || '',
  set: (uri) => {
    tv.value.sony_app_uris = {...(tv.value.sony_app_uris || {}), [mediaServerType.value]: uri}
  },
})

const sonyAppsDetected = computed(() => Boolean((tv.value.sony_available_apps || []).length))
const sonyAppMapped = computed(() => Boolean(selectedSonyAppUri.value))

watch(selectedTvSourceIndex, (i) => {
  tv.value.player_hdmi_input_id = i
})

watch(
    () => [tv.value.enabled, tv.value.model, tv.value.ip, tv.value.sony_psk, tv.value.startup_script].join('|'),
    () => {
      tvTested.value = false
      patchRoomReadiness('tv', localTvReadiness())
    },
)

function emptyTvForModel(model, enabled) {
  return {
    enabled,
    model,
    ip: '',
    mac: '',
    available_hdmi_inputs: [],
    player_hdmi_input_id: 0,
    startup_script: '',
    shutdown_script: '',
    sony_psk: '',
    sony_psk_configured: false,
    sony_app_uris: {},
    sony_available_apps: [],
  }
}

function onTvModelChange() {
  tv.value = tv.value.model === originalTv.value.model
      ? {...originalTv.value}
      : emptyTvForModel(tv.value.model, tv.value.enabled)
  selectedTvSourceIndex.value = tv.value.player_hdmi_input_id || 0
  tvTested.value = false
}

function roomStateLabel(state) {
  return t(`x-room-state-${state}`)
}

function roomStateClass(state) {
  return `room-state--${state}`
}

const ROOM_ACCENT_BY_STATE = {
  tested: 'panel-accent-ok',
  configured: 'panel-accent-info',
  incomplete: 'panel-accent-warn',
  disabled: 'panel-accent-dim',
}

function roomAccentClass(state) {
  return ROOM_ACCENT_BY_STATE[state] || 'panel-accent-dim'
}

async function configWithSection(section, value) {
  const latest = await api.getConfig()
  const nextConfig = {
    ...latest,
    [section]: {...value},
  }
  fullConfig.value = nextConfig
  return nextConfig
}

async function saveConfigSection(section, value) {
  const savedConfig = await saveSection(section, value)
  fullConfig.value = savedConfig
  return savedConfig
}

async function testTvConnection() {
  tvTestLoading.value = true
  try {
    const result = await api.testTvConnection(await configWithSection('tv', tv.value))
    if (result?.tv) {
      tv.value = {...result.tv}
      selectedTvSourceIndex.value = tv.value.player_hdmi_input_id || 0
    }
    // The reassignment above changes tv.value.ip, which the watch() below picks
    // up asynchronously (default 'pre' flush) and resets tvTested to false —
    // after nextTick() that pending reset has already run, so this write wins.
    await nextTick()
    tvTested.value = true
    toast.success(t('x-tv-connection-ok'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    tvTestLoading.value = false
  }
}

async function getTvSources() {
  tvSourcesLoading.value = true
  try {
    const updated = await api.getTvSources(await configWithSection('tv', tv.value))
    tv.value = {...(updated.tv || {})}
    fullConfig.value = updated
    selectedTvSourceIndex.value = tv.value.player_hdmi_input_id || 0
    toast.success(t('x-tv-inputs-detected'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    tvSourcesLoading.value = false
  }
}

async function getTvApps() {
  tvAppsLoading.value = true
  try {
    const updated = await api.getTvApps(await configWithSection('tv', tv.value))
    tv.value = {...(updated.tv || {})}
    fullConfig.value = updated
    toast.success(t('x-tv-apps-detected'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    tvAppsLoading.value = false
  }
}

async function tvSwitchInput() {
  try {
    await api.tvSwitchInput(await configWithSection('tv', tv.value))
    tvTested.value = true
    toast.success(t('x-tv-input-switched'))
  } catch (e) {
    toast.error(e.message)
  }
}

async function tvRestoreInput() {
  try {
    await api.tvRestoreInput(await configWithSection('tv', tv.value))
    tvTested.value = true
    toast.success(t('x-tv-input-restored'))
  } catch (e) {
    toast.error(e.message)
  }
}

async function saveTv() {
  const wasTested = tvTested.value
  try {
    const savedConfig = await saveConfigSection('tv', tv.value)
    tv.value = {...(savedConfig.tv || {})}
    originalRoomReadiness.value.tv = localTvReadiness()
    originalTv.value = {...(savedConfig.tv || {})}
    patchRoomReadiness('tv', originalRoomReadiness.value.tv)
    selectedTvSourceIndex.value = tv.value.player_hdmi_input_id || 0
    // Same race as testTvConnection above: reassigning tv.value here retriggers
    // the watch() that resets tvTested, even though nothing the user configured
    // actually changed — just persisted. Restore the pre-save tested state
    // after nextTick() so this write wins over that pending reset.
    await nextTick()
    tvTested.value = wasTested
    toast.success(t('x-common-saved'))
  } catch (e) {
    toast.error(e.message)
  }
}

/* AV state */
const av = ref({})
const originalAv = ref({})
const avModels = ref([])
const selectedAvSource = ref('')
const avPowerOnLoading = ref(false)
const avPowerOffLoading = ref(false)
const avSourcesLoading = ref(false)
const avHdmiLoading = ref(false)
const avTested = ref(false)
const trinnovMacManualEntry = ref(false)

const isTrinnovAv = computed(() => av.value.model === 'TRINNOV')
const trinnovMacAvailable = computed(() => Boolean((av.value.trinnov_mac || '').trim()))
const avPowerActionsLocked = computed(() => isTrinnovAv.value && !trinnovMacAvailable.value)
const trinnovMacFieldLocked = computed(() => isTrinnovAv.value && arpAvailable.value && !trinnovMacManualEntry.value)
const trinnovSourcesLocked = computed(() => (
    isTrinnovAv.value && !(av.value.available_hdmi_inputs || []).length
))

const avState = computed(() => {
  if (!av.value.enabled) return 'disabled'
  if (!av.value.model) return 'incomplete'
  if (av.value.model === 'SCRIPTS' && !av.value.power_on_command) return 'incomplete'
  if (av.value.model !== 'SCRIPTS' && !av.value.ip) return 'incomplete'
  return avTested.value ? 'tested' : 'configured'
})

watch(
    () => [av.value.enabled, av.value.model, av.value.ip, av.value.trinnov_mac, av.value.power_on_command, av.value.hdmi_input_command].join('|'),
    () => {
      avTested.value = false
      patchRoomReadiness('av', localAvReadiness())
    },
)

watch(
    () => [av.value.model, av.value.ip].join('|'),
    () => {
      trinnovMacManualEntry.value = false
    },
)

watch(
    [() => av.value.model, () => av.value.ip, devices],
    () => {
      autoFillTrinnovMac()
    },
)

function onAvSourceChange() {
  av.value.player_hdmi_input = selectedAvSource.value
}

function onAvModelChange() {
  selectedAvSource.value = ''
  av.value.player_hdmi_input = ''
  av.value.available_hdmi_inputs = []
  if (av.value.model === originalAv.value.model) {
    av.value = {...originalAv.value}
    selectedAvSource.value = av.value.player_hdmi_input || ''
    trinnovMacManualEntry.value = false
  } else if (av.value.model !== 'TRINNOV') {
    delete av.value.trinnov_mac
    trinnovMacManualEntry.value = false
  } else {
    autoFillTrinnovMac()
  }
  patchRoomReadiness('av', localAvReadiness())
}

function patchRoomReadiness(section, value) {
  patchSetupReadiness(section, value)
}

function sectionsMatchCurrentOriginal(section) {
  const current = section === 'tv' ? tv.value : av.value
  const original = section === 'tv' ? originalTv.value : originalAv.value
  return JSON.stringify(current || {}) === JSON.stringify(original || {})
}

function localTvReadiness() {
  if (sectionsMatchCurrentOriginal('tv') && originalRoomReadiness.value.tv) {
    return originalRoomReadiness.value.tv
  }
  if (!tv.value.enabled) return {status: 'disabled', detail: 'TV control disabled (optional)'}
  if (!tv.value.model) return {status: 'incomplete', detail: 'Model not selected'}
  if (tv.value.model === 'LG') {
    return tv.value.ip
        ? {status: 'configured', detail: `LG · ${tv.value.ip}`}
        : {status: 'incomplete', detail: 'IP address not set'}
  }
  if (tv.value.model === 'SONY') {
    return tv.value.ip && tv.value.sony_psk_configured
        ? {status: 'configured', detail: `SONY · ${tv.value.ip}`}
        : {status: 'incomplete', detail: 'IP address or PSK not set'}
  }
  if (tv.value.model === 'SCRIPTS') {
    return tv.value.startup_script
        ? {status: 'configured', detail: 'SCRIPTS'}
        : {status: 'incomplete', detail: 'Startup script not set'}
  }
  return {status: 'configured', detail: tv.value.model}
}

function localAvReadiness() {
  if (sectionsMatchCurrentOriginal('av') && originalRoomReadiness.value.av) {
    return originalRoomReadiness.value.av
  }
  if (!av.value.enabled) return {status: 'disabled', detail: 'AV control disabled (optional)'}
  if (!av.value.model) return {status: 'incomplete', detail: 'Model not selected'}
  if (av.value.model === 'SCRIPTS') {
    return av.value.power_on_command
        ? {status: 'configured', detail: 'SCRIPTS'}
        : {status: 'incomplete', detail: 'Power on script not set'}
  }
  if (!av.value.ip) return {status: 'incomplete', detail: 'IP address not set'}
  if (av.value.model === 'TRINNOV' && !(av.value.available_hdmi_inputs || []).length) {
    return {status: 'incomplete', detail: 'Source/profile not detected'}
  }
  return {status: 'configured', detail: `${av.value.model} · ${av.value.ip}`}
}

function trinnovDeviceForCurrentIp() {
  if (!isTrinnovAv.value || !av.value.ip) return null
  return devices.value.find((device) => device.ip === av.value.ip && device.mac) || null
}

function autoFillTrinnovMac() {
  if (!isTrinnovAv.value || trinnovMacAvailable.value) return
  const device = trinnovDeviceForCurrentIp()
  if (device?.mac) {
    av.value.trinnov_mac = device.mac
    trinnovMacManualEntry.value = false
  }
}

async function detectTrinnovMac() {
  if (!av.value.ip) {
    toast.error(t('x-av-trinnov-mac-missing-ip'))
    return
  }

  await scan()
  autoFillTrinnovMac()

  if (trinnovMacAvailable.value) {
    trinnovMacManualEntry.value = false
    toast.success(t('x-av-trinnov-mac-detected'))
  } else {
    trinnovMacManualEntry.value = true
    toast.error(t('x-av-trinnov-mac-not-found'))
  }
}

async function testAvPowerOn() {
  avPowerOnLoading.value = true
  try {
    await api.avPowerOn(await configWithSection('av', av.value))
    avTested.value = true
    toast.success(t('x-av-power-on-ok'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    avPowerOnLoading.value = false
  }
}

async function testAvPowerOff() {
  avPowerOffLoading.value = true
  try {
    await api.avPowerOff(await configWithSection('av', av.value))
    avTested.value = true
    toast.success(t('x-av-power-off-ok'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    avPowerOffLoading.value = false
  }
}

async function getAvSources() {
  avSourcesLoading.value = true
  try {
    const updated = await api.getAvSources(await configWithSection('av', av.value))
    av.value = {...(updated.av || {})}
    fullConfig.value = updated
    originalRoomReadiness.value.av = localAvReadiness()
    originalAv.value = {...(updated.av || {})}
    patchRoomReadiness('av', originalRoomReadiness.value.av)
    selectedAvSource.value = av.value.player_hdmi_input || ''
    toast.success(t('x-av-inputs-detected'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    avSourcesLoading.value = false
  }
}

async function testAvHdmi() {
  avHdmiLoading.value = true
  try {
    await api.avSwitchInput(await configWithSection('av', av.value))
    avTested.value = true
    toast.success(t('x-av-hdmi-ok'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    avHdmiLoading.value = false
  }
}

async function saveAv() {
  try {
    const savedConfig = await saveConfigSection('av', av.value)
    av.value = {...(savedConfig.av || av.value)}
    originalRoomReadiness.value.av = localAvReadiness()
    originalAv.value = {...av.value}
    patchRoomReadiness('av', originalRoomReadiness.value.av)
    toast.success(t('x-common-saved'))
  } catch (e) {
    toast.error(e.message)
  }
}

/* Lighting state */
const {
  lighting,
  entities: lightingEntities,
  entityFilter: lightingEntityFilter,
  entityOptions: lightingEntityOptions,
  state: lightingState,
  testLoading: lightingTestLoading,
  entitiesLoading: lightingEntitiesLoading,
  switchLoading: lightingSwitchLoading,
  load: loadLighting,
  isSelected: isLightingEntitySelected,
  toggleEntity: toggleLightingEntity,
  testConnection: testLightingConnection,
  detectEntities: detectLightingEntitiesRequest,
  switchLights,
  save: saveLightingSection,
} = useRoomLighting({
  configWithSection,
  saveConfigSection,
  onReadinessChange: (readiness) => patchRoomReadiness('lighting', readiness),
})

const lightingActionOptions = computed(() =>
    LIGHTING_ACTIONS.map((action) => ({value: action, label: t(`x-lighting-action-${action}`)}))
)

async function testLighting() {
  try {
    await testLightingConnection()
    toast.success(t('x-lighting-connection-ok'))
  } catch (e) {
    toast.error(e.message)
  }
}

async function detectLightingEntities() {
  try {
    const found = await detectLightingEntitiesRequest()
    toast.success(t('x-lighting-entities-detected', {count: found.length}))
  } catch (e) {
    toast.error(e.message)
  }
}

async function switchLighting(action) {
  try {
    await switchLights(action)
    toast.success(t(action === 'turn_on' ? 'x-lighting-turned-on' : 'x-lighting-turned-off'))
  } catch (e) {
    toast.error(e.message)
  }
}

async function saveLighting() {
  try {
    await saveLightingSection()
    toast.success(t('x-common-saved'))
  } catch (e) {
    toast.error(e.message)
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await api.getConfig()
    fullConfig.value = data
    tv.value = {...(data.tv || {})}
    originalTv.value = {...(data.tv || {})}
    av.value = {...(data.av || {})}
    originalAv.value = {...(data.av || {})}
    loadLighting(data)
    originalRoomReadiness.value = {
      tv: data.config_readiness?.tv || null,
      av: data.config_readiness?.av || null,
    }
    tvModels.value = data.tv_dirs || ['LG', 'SONY', 'SCRIPTS']
    avModels.value = data.av_dirs || []
    selectedTvSourceIndex.value = tv.value.player_hdmi_input_id || 0
    selectedAvSource.value = av.value.player_hdmi_input || ''
    arpAvailable.value = data.arp_available !== false
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.sala-view {
  position: relative;
  min-height: 100dvh;
}

.sala-scene-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-position: center;
  background-size: cover;
  opacity: 0.97;
  filter: saturate(1.2) contrast(1.04) brightness(1.12) sepia(0.08) hue-rotate(-5deg);
}

.sala-scene-bg::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 18% 26%, rgba(80, 122, 142, 0.18), transparent 34%),
  radial-gradient(circle at 78% 18%, rgba(245, 165, 36, 0.18), transparent 34%),
  radial-gradient(circle at 12% 8%, rgba(194, 161, 107, 0.13), transparent 32%);
}

.sala-scene-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(8, 16, 20, 0.6), rgba(32, 56, 68, 0.12) 46%, rgba(8, 16, 20, 0.34)),
  linear-gradient(180deg, rgba(35, 61, 74, 0.08), rgba(8, 16, 20, 0.18) 52%, rgba(6, 13, 17, 0.68));
}

.sala-view-body {
  position: relative;
  z-index: 1;
  padding: clamp(40px, 7vh, 78px) clamp(22px, 5vw, 76px) clamp(28px, 5vh, 54px);
}

.sala-kicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  gap: 9px;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(7, 11, 13, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.075);
  color: var(--accent-secondary);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  backdrop-filter: blur(8px);
  margin-bottom: 12px;
}

.sala-showcase-title {
  max-width: 1050px;
  margin: 0;
  color: var(--text-main);
  font-size: clamp(34px, 4.1vw, 62px);
  font-weight: 900;
  line-height: 0.96;
  letter-spacing: 0;
  text-wrap: balance;
  text-shadow: 0 30px 88px rgba(0, 0, 0, 0.62);
}

.sala-showcase-subtitle {
  max-width: 800px;
  margin: 12px 0 0;
  color: rgba(245, 247, 255, 0.78);
  font-size: clamp(15px, 1.15vw, 19px);
  line-height: 1.42;
  text-wrap: balance;
}

.sala-showcase-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.sala-showcase {
  display: flex;
  min-height: clamp(132px, 21dvh, 228px);
  flex-direction: column;
  justify-content: center;
  margin-bottom: clamp(16px, 2.2vh, 26px);
}

.sala-shell {
  display: grid;
  gap: 18px;
  width: min(100%, 1500px);
  max-width: none;
  padding: 14px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(13, 18, 20, 0.58), rgba(13, 18, 20, 0.22));
  border: 1px solid rgba(255, 255, 255, 0.085);
  box-shadow: 0 32px 90px rgba(0, 0, 0, 0.4),
  inset 0 1px 0 rgba(255, 255, 255, 0.045);
  backdrop-filter: blur(7px);
}

.sala-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(320px, 1fr) minmax(260px, 0.75fr);
  gap: 16px;
  align-items: start;
}

.room-device-card {
  min-width: 0;
}

.room-card-head {
  align-items: flex-start;
  gap: 14px;
}

.room-card-controls {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.room-card-sub {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
  margin: 4px 0 0;
}

.room-card-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--panel-border);
}

.room-disabled-body {
  display: grid;
  gap: 14px;
  justify-items: start;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.room-disabled-body p {
  margin: 0;
}

.room-state {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 22px;
  padding: 3px 7px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  color: var(--text-subtle);
  background: rgba(255, 255, 255, 0.035);
  font-size: 9px;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.room-state--tested {
  color: var(--status-success);
  border-color: rgba(55, 230, 138, 0.18);
  background: rgba(55, 230, 138, 0.08);
}

.room-state--configured {
  color: var(--status-info);
  border-color: rgba(48, 213, 200, 0.16);
  background: rgba(48, 213, 200, 0.07);
}

.room-state--incomplete {
  color: var(--status-warning);
  border-color: rgba(245, 165, 36, 0.24);
  background: rgba(245, 165, 36, 0.08);
}

.room-state--disabled {
  color: var(--text-subtle);
}

.lighting-fade-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.lighting-entity-list {
  display: grid;
  gap: 4px;
  max-height: 240px;
  overflow-y: auto;
  padding: 6px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.075);
  background: rgba(7, 11, 13, 0.32);
}

.lighting-entity {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: 8px;
  align-items: center;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}

.lighting-entity:hover {
  background: rgba(255, 255, 255, 0.04);
}

.lighting-entity input {
  grid-row: span 2;
}

.lighting-entity-name {
  color: var(--text-main);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.lighting-entity-id {
  color: var(--text-muted);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}

.room-help-column {
  display: grid;
  gap: 12px;
  position: sticky;
  top: 18px;
}

.room-help-card {
  padding: 12px;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: linear-gradient(165deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.005) 40%, transparent),
  var(--bg-panel);
  box-shadow: inset 0 1px 0 var(--panel-specular), 0 18px 40px -16px rgba(7, 11, 13, 0.65);
}

.room-help-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-main);
  font-size: 12px;
  font-weight: 750;
  margin: 0 0 10px;
}

.room-help-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 17px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.icon-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

@media (max-width: 1180px) {
  .sala-grid {
    grid-template-columns: minmax(280px, 1fr) minmax(280px, 1fr);
  }

  .room-help-column {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    position: static;
  }
}

@media (max-width: 860px) {
  .sala-grid,
  .room-help-column {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .icon-action-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
