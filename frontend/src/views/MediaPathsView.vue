<template>
  <div class="view-content view-ambient paths-view">
    <div :style="{ backgroundImage: `url(${heroBg})` }" class="ambient-bg"></div>
    <div :style="{ backgroundImage: `url(${heroBg})` }" class="paths-scene-bg"></div>

    <div class="view-body paths-view-body">
      <section class="paths-showcase">
        <h1 class="paths-showcase-title">{{ $t('x-paths-title') }}</h1>
        <p class="paths-showcase-subtitle">{{ $t('x-paths-subtitle') }}</p>
        <div class="paths-showcase-actions">
          <div
              :aria-label="$t('x-paths-active-provider', {server: mediaServerTypeLabel})"
              :class="['paths-provider-badge', serverIncomplete && 'is-pending']"
              :style="pathsProviderStyle"
          >
            <span aria-hidden="true" class="paths-provider-icon">
              <svg
                  v-if="pathsProviderIcon"
                  class="paths-provider-svg"
                  fill="currentColor"
                  viewBox="0 0 24 24"
              >
                <path :d="pathsProviderIcon.path"/>
              </svg>
              <Server v-else :size="18" :stroke-width="2.2"/>
            </span>
            <span class="paths-provider-copy">
              <span class="paths-provider-label">{{ mediaServerTypeLabel }}</span>
              <span class="paths-provider-state">
                {{ serverIncomplete ? $t('x-paths-provider-unavailable') : $t('x-paths-provider-active') }}
              </span>
            </span>
          </div>
          <HelpTooltip :text="$t('x-paths-tooltip-discover')">
            <IconActionButton
                :disabled="gateActive"
                :label="$t('x-paths-refresh-libraries')"
                :loading="libraryPathsLoading"
                :loading-label="$t('x-paths-library-picker-loading')"
                icon="refresh"
                @click="refreshDetectedLibraries"
            />
          </HelpTooltip>
          <span class="paths-stats">
            {{
              $t('x-paths-summary', {
                detected: detectedRows.length,
                verified: verifiedRouteCount,
                active: activeDetectedLibraryCount,
                pending: statusCounts.pending + statusCounts.stale + statusCounts.error + statusCounts.unconfigured
              })
            }}
          </span>
        </div>
      </section>

      <div v-if="loading" class="text-sm" style="color:var(--text-muted)">
        {{ $t('x-common-loading') }}
      </div>

      <template v-else>
        <div class="paths-kicker">
          <span class="s-dot dim"></span>
          <span>{{ $t('x-nav-config-section') }}</span>
        </div>
        <div class="paths-shell">
          <div v-if="gateActive" class="gate-panel">
            <p class="gate-title">{{ $t('x-setup-gate-title') }}</p>
            <p v-if="serverIncomplete" class="gate-reason">
              {{ $t('x-setup-gate-discovery', {server: mediaServerTypeLabel}) }}</p>
            <p v-if="playerIncomplete" class="gate-reason">{{ $t('x-setup-gate-testing') }}</p>
            <div class="flex gap-2 mt-3 flex-wrap">
              <button v-if="serverIncomplete" class="btn-ghost" @click="router.push('/media-server')">
                {{ $t('x-setup-gate-configure-server') }}
              </button>
              <button v-if="playerIncomplete" class="btn-ghost" @click="router.push('/media-player')">
                {{ $t('x-setup-gate-configure-player') }}
              </button>
            </div>
            <button class="gate-manual-link mt-3" @click="manualOverride = true">
              {{ $t('x-setup-gate-manual') }}
            </button>
          </div>

          <div class="paths-workspace">
            <section :class="libraryQueueAccentClass" class="panel library-queue">
              <div class="panel-head">
                <h2 class="panel-title">
                  <FolderTree :size="13" :stroke-width="2.3"/>
                  {{ $t('x-paths-library-queue-title') }}
                </h2>
              </div>
              <div class="panel-body">
                <div v-if="libraryPathsLoading" class="folder-loading queue-loading">
                  <span class="folder-loading-spinner"></span>{{ $t('x-paths-library-picker-loading') }}
                </div>

                <div v-else-if="libraryPathsError" class="queue-empty">
                  <AlertTriangle :size="18" :stroke-width="2"/>
                  <div>
                    <p class="queue-empty-title">{{ $t('x-paths-detected-error-title') }}</p>
                    <p class="queue-empty-copy">{{ libraryPathsError }}</p>
                  </div>
                </div>

                <div v-else-if="!detectedRows.length" class="queue-empty">
                  <Circle :size="18" :stroke-width="2"/>
                  <div>
                    <p class="queue-empty-title">{{ $t('x-paths-no-detected-title') }}</p>
                    <p class="queue-empty-copy">{{ $t('x-paths-no-detected-copy', {type: mediaServerTypeLabel}) }}</p>
                    <IconActionButton
                        :label="$t('x-paths-advanced-new')"
                        class="mt-3"
                        compact
                        icon="add"
                        @click="newManualMapping"
                    />
                  </div>
                </div>

                <div v-else class="library-list">
                  <button
                      v-for="row in detectedRows"
                      :key="row.key"
                      :class="['library-row', selectedKey === row.key && 'library-row--active']"
                      type="button"
                      @click="selectRow(row)"
                  >
                    <span :class="['state-dot', `state-dot--${row.status}`]">
                      <CheckCircle v-if="row.status === 'verified'" :size="15" :stroke-width="2.4"/>
                      <AlertTriangle v-else-if="row.status === 'error' || row.status === 'stale'" :size="15"
                                     :stroke-width="2.3"/>
                      <Clock3 v-else-if="row.status === 'pending'" :size="15" :stroke-width="2.3"/>
                      <EyeOff v-else-if="row.status === 'not_intercepted'" :size="15" :stroke-width="2.3"/>
                      <Circle v-else :size="15" :stroke-width="2.3"/>
                    </span>
                    <span class="library-row-main">
                      <span class="library-row-name">{{ row.name }}</span>
                      <span class="library-row-path mono">{{ row.source_path }}</span>
                    </span>
                    <span :class="['state-label', `state-label--${row.status}`]">
                      {{ statusLabel(row.status) }}
                    </span>
                  </button>
                </div>

                <div v-if="manualRows.length" class="manual-list">
                  <p class="manual-list-title">{{ $t('x-paths-manual-section') }}</p>
                  <button
                      v-for="row in manualRows"
                      :key="row.key"
                      :class="['library-row', selectedKey === row.key && 'library-row--active']"
                      type="button"
                      @click="selectRow(row)"
                  >
                    <span :class="['state-dot', `state-dot--${row.status}`]">
                      <CheckCircle v-if="row.status === 'verified'" :size="15" :stroke-width="2.4"/>
                      <AlertTriangle v-else-if="row.status === 'error' || row.status === 'stale'" :size="15"
                                     :stroke-width="2.3"/>
                      <Clock3 v-else-if="row.status === 'pending'" :size="15" :stroke-width="2.3"/>
                      <EyeOff v-else-if="row.status === 'not_intercepted'" :size="15" :stroke-width="2.3"/>
                      <Circle v-else :size="15" :stroke-width="2.3"/>
                    </span>
                    <span class="library-row-main">
                      <span class="library-row-name">{{ row.name }}</span>
                      <span class="library-row-path mono">{{ row.source_path }}</span>
                    </span>
                    <span :class="['state-label', `state-label--${row.status}`]">
                      {{ statusLabel(row.status) }}
                    </span>
                  </button>
                </div>

                <div class="queue-secondary">
                  <IconActionButton
                      :label="$t('x-paths-advanced-new')"
                      compact
                      icon="add"
                      @click="newManualMapping"
                  />
                </div>
              </div>
            </section>

            <section :class="resolutionAccentClass" class="panel resolution-panel">
              <div class="panel-head">
                <h2 class="panel-title">
                  <Route :size="13" :stroke-width="2.3"/>
                  {{ advancedMode ? $t('x-paths-advanced-title') : $t('x-paths-resolution-title') }}
                </h2>
              </div>
              <div class="panel-body">
                <div v-if="!editing" class="resolution-empty">
                  <FolderOpen :size="24" :stroke-width="1.8"/>
                  <p>{{ $t('x-paths-select-library') }}</p>
                </div>

                <template v-else>
                  <div class="resolution-head">
                    <div>
                      <p v-if="!advancedMode" class="resolution-name">{{ form.name }}</p>
                      <p class="resolution-sub">
                        {{
                          advancedMode ? $t('x-paths-advanced-copy') : $t('x-paths-resolution-copy', {type: mediaServerTypeLabel})
                        }}
                      </p>
                    </div>
                    <HelpTooltip v-if="!advancedMode" :text="$t('x-paths-tooltip-edit-server-path')">
                      <IconActionButton
                          :label="$t('x-paths-open-advanced')"
                          compact
                          icon="edit"
                          @click="advancedMode = true"
                      />
                    </HelpTooltip>
                  </div>

                  <div v-if="advancedMode" class="advanced-mode-panel">
                    <div>
                      <div class="advanced-mode-kicker">{{ $t('x-paths-advanced-active') }}</div>
                      <label class="form-label" for="path-name">{{ $t('x-paths-field-name') }}</label>
                      <input
                          id="path-name"
                          v-model="form.name"
                          :disabled="gateActive"
                          class="form-input"
                          type="text"
                      />
                    </div>
                    <button
                        v-if="selectedKey?.startsWith('source:')"
                        class="btn-link advanced-mode-exit"
                        @click="advancedMode = false"
                    >
                      {{ $t('x-paths-guided-mode') }}
                    </button>
                  </div>

                  <div class="access-step">
                    <div class="access-step-main">
                      <div class="step-badge">2</div>
                      <Shield :size="18" :stroke-width="2"/>
                      <div class="access-step-copy">
                        <p class="access-step-title">{{ $t('x-paths-network-step-title') }}</p>
                        <p class="access-step-sub">
                          {{ smbEnabled ? $t('x-paths-smb-active-copy') : $t('x-paths-smb-nfs-hint') }}
                        </p>
                      </div>
                      <label class="access-toggle">
                        <input v-model="smbEnabled" type="checkbox"/>
                        <span>{{ $t('x-paths-smb-toggle') }}</span>
                      </label>
                    </div>

                    <div class="access-config">
                      <template v-if="smbEnabled">
                        <div class="smb-form-grid">
                          <div>
                            <label class="form-label" for="smb-username">{{ $t('x-paths-smb-username') }}</label>
                            <input id="smb-username" v-model="smbUsernameInput" autocomplete="username"
                                   class="form-input" type="text"/>
                          </div>

                          <div>
                            <label class="form-label" for="smb-password">{{ $t('x-paths-smb-password') }}</label>
                            <input id="smb-password" v-model="smbPassword" autocomplete="current-password"
                                   class="form-input" type="password"/>
                            <p v-if="smbPasswordConfigured" class="section-hint mt-2">
                              {{ $t('x-paths-smb-configured-hint') }}
                            </p>
                          </div>
                        </div>

                        <div class="flex items-center gap-2 mt-3">
                          <label class="flex items-center gap-2" style="cursor:pointer">
                            <input v-model="preMountSmb" type="checkbox"/>
                            <span class="body-text">{{ $t('x-paths-smb-pre-mount') }}</span>
                          </label>
                          <HelpTooltip :text="$t('x-paths-tooltip-smb-pre-mount')"/>
                        </div>
                      </template>

                      <div class="access-actions">
                        <button :disabled="authSaveLoading" class="btn-ghost" @click="saveAuthPanel">
                          {{ $t('x-paths-auth-save') }}
                        </button>
                        <HelpTooltip v-if="smbEnabled && (smbUsername || smbPasswordConfigured)"
                                     :text="$t('x-paths-tooltip-smb-clear')">
                          <IconActionButton
                              :disabled="authSaveLoading"
                              :label="$t('x-paths-smb-clear')"
                              icon="clear"
                              @click="clearCredentials"
                          />
                        </HelpTooltip>
                      </div>
                    </div>
                  </div>

                  <div class="route-rails">
                    <div class="route-rail">
                      <div class="route-rail-label">{{ $t('x-paths-server-rail', {type: mediaServerTypeLabel}) }}</div>
                      <div v-if="advancedMode" class="route-input-row">
                        <input
                            id="path-source"
                            v-model="form.source_path"
                            :disabled="gateActive"
                            class="form-input route-input"
                            type="text"
                        />
                      </div>
                      <div v-else class="route-value mono">{{ form.source_path }}</div>
                    </div>

                    <div aria-hidden="true" class="route-link"></div>

                    <div class="route-rail route-rail--oppo">
                      <div class="route-rail-label">{{ $t('x-paths-oppo-rail', {mode: networkModeLabel}) }}</div>
                      <div class="route-input-row">
                        <input
                            id="path-player"
                            v-model="form.player_path"
                            :disabled="gateActive"
                            class="form-input route-input mono"
                            type="text"
                        />
                        <IconActionButton
                            :disabled="gateActive"
                            :label="showNav ? $t('x-paths-close-browser') : $t('x-paths-browse-oppo')"
                            compact
                            icon="folder"
                            @click="toggleNav"
                        />
                      </div>
                      <p class="section-hint mt-2">{{ $t('x-paths-oppo-browser-hint') }}</p>
                    </div>
                  </div>

                  <div class="power-switch-block mt-3">
                    <div class="form-label label-with-help">
                      <label for="path-power-switch">{{ $t('x-paths-power-switch') }}</label>
                      <HelpTooltip :text="$t('x-paths-tooltip-power-switch')"/>
                    </div>
                    <template v-if="homeAssistantReady">
                      <div class="route-input-row">
                        <input
                            id="path-power-switch"
                            v-model.trim="form.power_switch_entity_id"
                            :disabled="gateActive"
                            :placeholder="$t('x-paths-power-switch-placeholder')"
                            autocomplete="off"
                            class="form-input route-input mono"
                            list="path-power-switch-options"
                            type="text"
                        />
                        <IconActionButton
                            :disabled="gateActive || !form.power_switch_entity_id || !form.player_path"
                            :label="$t('x-paths-power-on')"
                            :loading="powerOnLoading"
                            :loading-label="$t('x-paths-powering-on')"
                            compact
                            icon="power-on"
                            @click="powerOnMediaSource"
                        />
                      </div>
                      <datalist id="path-power-switch-options">
                        <option v-for="entity in powerSwitches" :key="entity.entity_id" :value="entity.entity_id">
                          {{ entity.name }} · {{ entity.state }}
                        </option>
                      </datalist>
                      <p class="section-hint mt-2">{{ $t('x-paths-power-switch-hint') }}</p>
                    </template>
                    <p v-else class="section-hint">{{ $t('x-paths-power-switch-needs-ha') }}</p>
                  </div>

                  <div v-if="showNav" class="folder-nav mt-3">
                    <div v-if="navLoading" class="folder-loading">
                      <span class="folder-loading-spinner"></span>{{ $t('x-paths-nav-loading') }}
                    </div>
                    <div v-else-if="navError" class="folder-error">{{ navErrorLabel }}</div>
                    <template v-else>
                      <button
                          v-for="(folder, fi) in navDirs"
                          :key="fi"
                          class="folder-item"
                          type="button"
                          @click="navigateToFolder(folder.Foldername)"
                      >
                        <FolderOpen v-if="folder.Foldername !== '..'" :size="14" :stroke-width="2"/>
                        <span v-else class="folder-up">..</span>
                        <span>{{ folder.Foldername }}</span>
                      </button>
                      <div v-if="!navDirs.length" class="folder-empty">{{ $t('x-paths-no-subfolders') }}</div>
                    </template>
                  </div>

                  <div v-if="playerSuggestion && !form.player_path" class="suggestion-card mt-3">
                    <div>
                      <p class="suggestion-title">{{ $t('x-paths-player-suggestion-title') }}</p>
                      <p class="suggestion-path mono">{{ playerSuggestion }}</p>
                    </div>
                    <IconActionButton
                        :label="$t('x-paths-use-suggestion')"
                        compact
                        icon="check"
                        @click="acceptPlayerSuggestion"
                    />
                  </div>

                  <div v-if="preview" class="path-preview mt-3">
                    <div class="preview-label">{{ $t('x-paths-preview-example') }}</div>
                    <div class="preview-row">
                      <span class="preview-key">{{ mediaServerTypeLabel }}</span>
                      <span class="mono preview-val">{{ preview.source_prefix }}</span>
                    </div>
                    <div class="preview-row preview-arrow">to</div>
                    <div class="preview-row">
                      <span class="preview-key">{{ $t('x-paths-preview-player') }}</span>
                      <span class="mono preview-val">{{ preview.player_prefix }}</span>
                    </div>
                  </div>

                  <p v-if="form.verified && !formDirty" class="verify-note verify-note--ok">
                    {{ $t('x-paths-path-verified') }}
                  </p>
                  <p v-else-if="formDirty && originalVerified" class="verify-note verify-note--stale">
                    {{ $t('x-paths-path-stale') }}
                  </p>

                  <div class="resolution-actions">
                    <HelpTooltip :text="$t('x-paths-tooltip-test-path', {server: mediaServerTypeLabel})">
                      <IconActionButton
                          :disabled="gateActive || !canTest"
                          :label="$t('x-paths-test-path')"
                          :loading="testLoading"
                          :loading-label="$t('x-common-testing')"
                          icon="test"
                          @click="testPath"
                      />
                    </HelpTooltip>
                    <button :disabled="gateActive || !canSaveDraft" class="btn-ghost" @click="savePath(false)">
                      {{ $t('x-paths-save-draft') }}
                    </button>
                    <button v-if="editIndex !== null" class="btn-ghost btn-danger-inline" @click="deleteCurrentMapping">
                      {{ $t('x-common-delete') }}
                    </button>
                  </div>

                  <p class="section-hint mt-2">{{ $t('x-paths-test-hint') }}</p>

                  <div v-if="testResult" class="diag-inline mt-3">
                    <p class="diag-inline-label">{{ $t('x-diag-reason') }}</p>
                    <p class="diag-inline-reason">{{ diagnosticReason(testResult) }}</p>
                    <p class="diag-inline-label mt-2">{{ $t('x-diag-suggestion') }}</p>
                    <p class="diag-inline-suggestion">{{ diagnosticSuggestion(testResult) }}</p>
                  </div>
                </template>
              </div>
            </section>

            <aside class="paths-help-column">
              <details class="secondary-details" open>
                <summary>
                  <span class="summary-label"><ListFilter :size="13"
                                                          :stroke-width="2.3"/>{{ $t('x-paths-library-filter-title') }}</span>
                  <span v-if="librariesSaving" class="inline-saving">
                    <span class="folder-loading-spinner"></span>{{ $t('x-media-server-libraries-saving') }}
                  </span>
                </summary>
                <div class="secondary-details-body">
                  <p class="secondary-details-copy">{{ $t('x-paths-library-filter-copy') }}</p>
                  <div v-if="librariesLoading" class="body-text">
                    {{ $t('x-media-server-loading-devices') }}
                  </div>
                  <template v-else>
                    <div class="flex items-center gap-2 mb-3">
                      <label class="flex items-center gap-2" style="cursor:pointer">
                        <input v-model="useAllLibraries" :disabled="gateActive" type="checkbox"/>
                        <span class="body-text">{{ $t('x-media-server-use-all-libraries') }}</span>
                      </label>
                      <HelpTooltip :text="$t('x-paths-tooltip-all-libraries')"/>
                    </div>
                    <div v-if="libraries.length" class="library-filter-list">
                      <label
                          v-for="lib in libraries"
                          :key="lib.id || lib.name"
                          class="library-filter-row"
                      >
                        <input v-model="lib.active" :disabled="useAllLibraries || gateActive" type="checkbox"/>
                        <span class="body-text">{{ lib.name }}</span>
                      </label>
                    </div>
                    <p v-else class="caption">{{ $t('x-media-server-no-libraries') }}</p>
                    <div class="access-actions">
                      <button
                          :disabled="gateActive || librariesSaving || !libraryFilterDirty"
                          class="btn-ghost"
                          @click="saveLibraries"
                      >
                        {{ $t('x-paths-library-filter-save') }}
                      </button>
                      <span v-if="libraryFilterDirty" class="inline-saving">{{ $t('x-paths-unsaved-changes') }}</span>
                    </div>
                  </template>
                </div>
              </details>

              <details :open="statusLegendOpen" class="status-legend">
                <summary><span class="summary-label"><Info :size="13"
                                                           :stroke-width="2.3"/>{{ $t('x-paths-status-legend-title') }}</span>
                </summary>
                <div class="status-legend-list">
                  <div
                      v-for="item in statusLegendItems"
                      :key="item.status"
                      class="status-legend-row"
                  >
                    <span :class="['state-dot', `state-dot--${item.status}`]">
                      <CheckCircle v-if="item.status === 'verified'" :size="15" :stroke-width="2.4"/>
                      <AlertTriangle v-else-if="item.status === 'error' || item.status === 'stale'" :size="15"
                                     :stroke-width="2.3"/>
                      <Clock3 v-else-if="item.status === 'pending'" :size="15" :stroke-width="2.3"/>
                      <EyeOff v-else-if="item.status === 'not_intercepted'" :size="15" :stroke-width="2.3"/>
                      <Circle v-else :size="15" :stroke-width="2.3"/>
                    </span>
                    <span class="status-legend-copy">
                      <span :class="['state-label', `state-label--${item.status}`]">{{ item.label }}</span>
                      <span>{{ item.copy }}</span>
                    </span>
                  </div>
                </div>
              </details>
            </aside>
          </div>

          <StepNav :current-step="3"/>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import {computed, onMounted, ref} from 'vue'
import {useI18n} from 'vue-i18n'
import {useRouter} from 'vue-router'
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Clock3,
  EyeOff,
  FolderOpen,
  FolderTree,
  Info,
  ListFilter,
  Route,
  Server,
  Shield,
} from '@lucide/vue'
import {siEmby, siJellyfin, siPlex} from 'simple-icons'
import {api} from '../api/index.js'
import heroBg from '../assets/backgrounds/bg-media-server.png'
import {useToast} from '../composables/useToast.js'
import StepNav from '../components/StepNav.vue'
import HelpTooltip from '../components/HelpTooltip.vue'
import IconActionButton from '../components/IconActionButton.vue'
import {useSetupReadiness} from '../composables/useSetupReadiness.js'
import {useMediaPathWorkflow} from '../composables/useMediaPathWorkflow.js'
import {useConfigSectionSave} from '../composables/useConfigSectionSave.js'
import {useDiagnosticText} from '../composables/useDiagnosticText.js'
import {useMediaServerBrand} from '../composables/useMediaServerBrand.js'
import {useActiveMediaServer} from '../composables/useActiveMediaServer.js'
import {homeAssistantConfigured} from '../composables/useHomeAssistant.js'

const {t} = useI18n()
const toast = useToast()
const router = useRouter()
const {readiness} = useSetupReadiness()
const {saveSection} = useConfigSectionSave()
const {diagnosticReason, diagnosticSuggestion} = useDiagnosticText()
const manualOverride = ref(false)

const setupReadyStatuses = new Set(['configured', 'verified', 'stale'])
const setupSectionUsable = (section) => setupReadyStatuses.has(section?.status)

const gateActive = computed(() =>
        !manualOverride.value && (
        !setupSectionUsable(readiness.value?.media_server) ||
        !setupSectionUsable(readiness.value?.media_player)
        )
)
const serverIncomplete = computed(() => !setupSectionUsable(readiness.value?.media_server))
const playerIncomplete = computed(() => !setupSectionUsable(readiness.value?.media_player))

const loading = ref(true)
const libraryPathsLoading = ref(false)
const libraryPathsError = ref(null)
const librariesLoading = ref(false)

const preMountSmb = ref(false)
const smbUsername = ref('')
const smbUsernameInput = ref('')
const smbPassword = ref('')
const smbPasswordConfigured = ref(false)
const authSaveLoading = ref(false)

const libraries = ref([])
const useAllLibraries = ref(true)
const librariesSaving = ref(false)
const savedLibraryFilter = ref({useAllLibraries: true, libraries: []})
const fullConfig = ref({})

const {
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
  smbEnabled,
  canTest,
  canSaveDraft,
  detectedRows,
  manualRows,
  statusCounts,
  initialize,
  setDetectedLibraries,
  selectRow,
  newManualMapping,
  acceptPlayerSuggestion,
  testPath: runPathTest,
  powerOnSource,
  savePath: persistPath,
  deleteCurrentMapping: removeCurrentMapping,
  saveNetworkAccess,
  clearCredentialsAndInvalidate,
  toggleNav,
  navigateToFolder,
} = useMediaPathWorkflow({
  api,
  defaultProtocol,
  isLibraryIntercepted,
  persistRouteMappings,
  persistNetworkAccess,
  clearSmbCredentials: api.clearSmbCredentials,
})

const {provider: activeProvider} = useActiveMediaServer(() => fullConfig.value)
const {brand: mediaServerBrand} = useMediaServerBrand(() => fullConfig.value?.media_servers?.active)
const mediaServerTypeLabel = computed(() => mediaServerBrand.value.label)
const pathsProviderIcons = {
  emby: siEmby,
  jellyfin: siJellyfin,
  plex: siPlex,
}
const pathsProviderIcon = computed(() => pathsProviderIcons[mediaServerBrand.value.brand] || null)
const pathsProviderStyle = computed(() => {
  if (!pathsProviderIcon.value?.hex) return undefined
  return {'--paths-provider-color': `#${pathsProviderIcon.value.hex}`}
})

const networkModeLabel = computed(() => smbEnabled.value ? 'SMB/CIFS' : 'NFS')
const activeDetectedLibraryCount = computed(() => detectedRows.value.filter((row) => row.intercepted).length)
const verifiedRouteCount = computed(() => detectedRows.value.filter((row) => row.mapping?.verified).length + manualRows.value.filter((row) => row.mapping?.verified).length)
const libraryFilterDirty = computed(() => libraryFilterSnapshot() !== savedLibraryFilterSnapshot())
const statusLegendOpen = computed(() =>
    !!(statusCounts.value.not_intercepted || statusCounts.value.pending || statusCounts.value.stale || statusCounts.value.error)
)
const navErrorLabel = computed(() => {
  if (!navError.value) return ''
  return navError.value.status === 503 ? t('x-paths-nav-error') : t('x-paths-nav-mount-error')
})
const libraryQueueAccentClass = computed(() => {
  if (libraryPathsError.value) return 'panel-accent-err'
  if (statusCounts.value.error) return 'panel-accent-err'
  if (statusCounts.value.stale || statusCounts.value.pending) return 'panel-accent-warn'
  if (!detectedRows.value.length) return 'panel-accent-dim'
  return 'panel-accent-ok'
})

const resolutionAccentClass = computed(() => {
  if (!editing.value) return 'panel-accent-dim'
  if (form.value.verified && !formDirty.value) return 'panel-accent-ok'
  if (formDirty.value && originalVerified.value) return 'panel-accent-warn'
  return 'panel-accent-info'
})

const statusLegendItems = computed(() => [
  {status: 'verified', label: statusLabel('verified'), copy: t('x-paths-status-legend-verified')},
  {status: 'not_intercepted', label: statusLabel('not_intercepted'), copy: t('x-paths-status-legend-not-intercepted')},
  {status: 'pending', label: statusLabel('pending'), copy: t('x-paths-status-legend-pending')},
  {status: 'stale', label: statusLabel('stale'), copy: t('x-paths-status-legend-stale')},
  {status: 'unconfigured', label: statusLabel('unconfigured'), copy: t('x-paths-status-legend-unconfigured')},
  {status: 'error', label: statusLabel('error'), copy: t('x-paths-status-legend-error')},
])

function statusLabel(status) {
  return t(`x-paths-state-${status}`)
}

function defaultProtocol() {
  return fullConfig.value.oppo?.use_smb ? 'cifs' : 'nfs'
}

function isLibraryIntercepted(libraryPath) {
  if (useAllLibraries.value) return true
  const libraryName = String(libraryPath?.library_name || '').trim()
  const library = libraries.value.find((candidate) => candidate.name === libraryName)
  return !!library?.active
}

function libraryFilterSnapshot() {
  return JSON.stringify({
    useAllLibraries: useAllLibraries.value,
    libraries: libraries.value.map((library) => ({
      id: String(library.id || ''),
      name: String(library.name || ''),
      active: !!library.active,
    })),
  })
}

function savedLibraryFilterSnapshot() {
  return JSON.stringify(savedLibraryFilter.value)
}

function rememberSavedLibraryFilter() {
  savedLibraryFilter.value = {
    useAllLibraries: useAllLibraries.value,
    libraries: libraries.value.map((library) => ({
      id: String(library.id || ''),
      name: String(library.name || ''),
      active: !!library.active,
    })),
  }
}

async function loadLibraries() {
  librariesLoading.value = true
  try {
    const full = await api.getConfigWithLibraries()
    fullConfig.value = full
    libraries.value = activeProvider.value.playback.libraries
    useAllLibraries.value = activeProvider.value.playback.use_all_libraries
  } catch {
    libraries.value = []
  } finally {
    librariesLoading.value = false
    rememberSavedLibraryFilter()
  }
}

async function fetchDetectedLibraries() {
  libraryPathsLoading.value = true
  libraryPathsError.value = null
  try {
    return await api.getLibraryPaths()
  } catch (e) {
    libraryPathsError.value = e.message
    return []
  } finally {
    libraryPathsLoading.value = false
  }
}

async function refreshDetectedLibraries() {
  setDetectedLibraries(await fetchDetectedLibraries())
}

async function persistRouteMappings(nextMappings) {
  const saved = await saveSection('path-mappings', {path_mappings: nextMappings})
  fullConfig.value = saved
  return saved
}

async function persistNetworkAccess({preMountSmb: nextPreMountSmb, username, password, pathMappings}) {
  const oppo = {}
  if (nextPreMountSmb !== null) oppo.pre_mount_smb = nextPreMountSmb
  const saved = await saveSection('network-access', {
    oppo,
    smb: {username, password},
    path_mappings: pathMappings,
  })
  fullConfig.value = saved
  return saved
}

async function saveLibraries() {
  librariesSaving.value = true
  try {
    const librariesSnapshot = libraries.value.map((library) => ({...library}))
    const useAllSnapshot = useAllLibraries.value
    const saved = await saveSection('playback-libraries', {
      libraries: librariesSnapshot,
      use_all_libraries: useAllSnapshot,
    })
    fullConfig.value = saved
    rememberSavedLibraryFilter()
    toast.success(t('x-common-saved'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    librariesSaving.value = false
  }
}

async function testPath() {
  try {
    await runPathTest()
    toast.success(t('x-paths-path-ok'))
  } catch (e) {
    if (!testResult.value?.reason) {
      testResult.value = {
        reason: e.message,
        suggestion: t('x-paths-generic-test-suggestion'),
      }
    }
  }
}

async function savePath(requireVerified, showToast = true) {
  await persistPath(requireVerified)
  if (showToast) toast.success(t('x-common-saved'))
}

async function deleteCurrentMapping() {
  await removeCurrentMapping()
  toast.success(t('x-common-saved'))
}

async function saveAuthPanel() {
  authSaveLoading.value = true
  try {
    const usernameToSubmit = smbEnabled.value ? smbUsernameInput.value : smbUsername.value
    const smbAccessChanged = preMountSmb.value !== (fullConfig.value.oppo?.pre_mount_smb ?? false)
        || usernameToSubmit !== smbUsername.value
        || !!smbPassword.value
    const savedConfig = await saveNetworkAccess({
      smbAccessChanged,
      preMountSmb: preMountSmb.value,
      username: usernameToSubmit,
      password: smbPassword.value,
    })
    fullConfig.value = savedConfig
    smbUsername.value = savedConfig.smb?.username ?? ''
    smbUsernameInput.value = savedConfig.smb?.username ?? ''
    smbPasswordConfigured.value = savedConfig.smb?.password_configured ?? false
    smbPassword.value = ''
    toast.success(t('x-common-saved'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    authSaveLoading.value = false
  }
}

async function clearCredentials() {
  authSaveLoading.value = true
  try {
    const savedConfig = await clearCredentialsAndInvalidate()
    fullConfig.value = savedConfig
    smbUsername.value = ''
    smbUsernameInput.value = ''
    smbPasswordConfigured.value = false
    toast.success(t('x-paths-smb-cleared'))
  } catch (e) {
    toast.error(e.message)
  } finally {
    authSaveLoading.value = false
  }
}

const homeAssistantReady = computed(() => homeAssistantConfigured(fullConfig.value?.home_assistant))
const powerSwitches = ref([])

// Suggestions for the power-switch field; failing to list them (Home
// Assistant down) only loses the suggestions, the field still works.
async function loadPowerSwitches(config) {
  if (!homeAssistantConfigured(config?.home_assistant)) return
  try {
    const result = await api.getHomeAssistantEntities(config, ['switch', 'input_boolean'])
    powerSwitches.value = result?.entities || []
  } catch {
    powerSwitches.value = []
  }
}

async function powerOnMediaSource() {
  try {
    await powerOnSource()
    toast.success(t('x-paths-powered-on'))
  } catch (e) {
    toast.error(e.message)
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await api.getConfig()
    fullConfig.value = data
    smbUsername.value = data.smb?.username ?? ''
    smbUsernameInput.value = data.smb?.username ?? ''
    smbPasswordConfigured.value = data.smb?.password_configured ?? false
    preMountSmb.value = data.oppo?.pre_mount_smb ?? false
    const [, detectedLibraries] = await Promise.all([loadLibraries(), fetchDetectedLibraries()])
    initialize(data, detectedLibraries)
    loadPowerSwitches(data)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.paths-view {
  position: relative;
  min-height: 100dvh;
}

.paths-scene-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-position: center;
  background-size: cover;
  opacity: 0.97;
  filter: saturate(1.2) contrast(1.04) brightness(1.12) sepia(0.08) hue-rotate(-5deg);
}

.paths-scene-bg::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 18% 26%, rgba(80, 122, 142, 0.18), transparent 34%),
  radial-gradient(circle at 78% 18%, rgba(245, 165, 36, 0.18), transparent 34%),
  radial-gradient(circle at 12% 8%, rgba(194, 161, 107, 0.13), transparent 32%);
}

.paths-scene-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(8, 16, 20, 0.6), rgba(32, 56, 68, 0.12) 46%, rgba(8, 16, 20, 0.34)),
  linear-gradient(180deg, rgba(35, 61, 74, 0.08), rgba(8, 16, 20, 0.18) 52%, rgba(6, 13, 17, 0.68));
}

.paths-view-body {
  position: relative;
  z-index: 1;
  padding: clamp(40px, 7vh, 78px) clamp(22px, 5vw, 76px) clamp(28px, 5vh, 54px);
}

.paths-kicker {
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

.paths-showcase-title {
  max-width: 1120px;
  margin: 0;
  color: var(--text-main);
  font-size: clamp(34px, 4.1vw, 62px);
  font-weight: 900;
  line-height: 0.96;
  letter-spacing: 0;
  text-wrap: balance;
  text-shadow: 0 30px 88px rgba(0, 0, 0, 0.62);
}

.paths-showcase-subtitle {
  max-width: 720px;
  margin: 12px 0 0;
  color: rgba(245, 247, 255, 0.78);
  font-size: clamp(15px, 1.15vw, 19px);
  line-height: 1.42;
  text-wrap: balance;
}

.paths-showcase-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.paths-provider-badge {
  --paths-provider-color: var(--accent-primary);
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(7, 11, 13, 0.4);
  border: 1px solid color-mix(in srgb, var(--paths-provider-color) 26%, rgba(255, 255, 255, 0.09));
  color: var(--text-main);
  box-shadow: 0 14px 32px color-mix(in srgb, var(--paths-provider-color) 13%, transparent);
  backdrop-filter: blur(8px);
}

.paths-provider-badge.is-pending {
  opacity: 0.68;
  filter: grayscale(0.35);
}

.paths-provider-icon {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  color: var(--paths-provider-color);
  flex: 0 0 auto;
}

.paths-provider-svg {
  width: 20px;
  height: 20px;
}

.paths-provider-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.paths-provider-label {
  font-size: 12px;
  font-weight: 900;
  line-height: 1;
}

.paths-provider-state {
  color: rgba(245, 247, 255, 0.62);
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
}

.paths-stats {
  min-height: 38px;
  padding: 10px 13px;
  border-radius: 999px;
  background: rgba(7, 11, 13, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.075);
  color: rgba(245, 247, 255, 0.72);
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.paths-showcase {
  display: flex;
  min-height: clamp(132px, 21dvh, 228px);
  flex-direction: column;
  justify-content: center;
  margin-bottom: clamp(16px, 2.2vh, 26px);
}

.summary-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.paths-shell {
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

.paths-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 0.72fr) minmax(470px, 1.35fr) minmax(280px, 0.82fr);
  gap: 18px;
  align-items: start;
}

@media (max-width: 1180px) {
  .paths-workspace {
    grid-template-columns: minmax(280px, 0.75fr) minmax(0, 1.25fr);
  }

  .paths-help-column {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    position: static;
  }
}

@media (max-width: 940px) {
  .paths-workspace {
    grid-template-columns: 1fr;
  }

  .paths-help-column {
    grid-template-columns: 1fr;
  }
}

.gate-panel {
  background: rgba(245, 165, 36, 0.07);
  border: 1px solid rgba(245, 165, 36, 0.25);
  border-radius: 8px;
  padding: 16px;
}

.gate-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--status-warning);
  margin-bottom: 8px;
}

.gate-reason {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
  line-height: 1.5;
}

.gate-manual-link,
.btn-link {
  font-size: 11px;
  color: var(--text-subtle);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-family: var(--font);
  text-decoration: underline;
}

.gate-manual-link:hover,
.btn-link:hover {
  color: var(--text-muted);
}

.queue-loading {
  padding: 2px 0;
}

.queue-empty {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  color: var(--text-muted);
  padding: 6px 0 2px;
}

.queue-empty svg {
  color: var(--text-subtle);
  flex-shrink: 0;
  margin-top: 2px;
}

.queue-empty-title {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
  margin: 0 0 3px;
}

.queue-empty-copy {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}

.library-list,
.manual-list {
  display: grid;
  gap: 8px;
}

.manual-list {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--panel-border);
}

.manual-list-title {
  font-size: 10px;
  font-weight: 750;
  color: var(--text-subtle);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin: 0 0 8px;
}

.queue-secondary {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--panel-border);
}

.paths-help-column {
  display: grid;
  gap: 12px;
  align-self: start;
  position: sticky;
  top: 18px;
}

@media (max-width: 1180px) {
  .paths-help-column {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    position: static;
  }
}

@media (max-width: 940px) {
  .paths-help-column {
    grid-template-columns: 1fr;
  }
}

.status-legend {
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: linear-gradient(165deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.005) 40%, transparent),
  var(--bg-panel);
  box-shadow: inset 0 1px 0 var(--panel-specular), 0 18px 40px -16px rgba(7, 11, 13, 0.65);
}

.status-legend summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  color: var(--text-main);
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
  list-style: none;
}

.status-legend summary::-webkit-details-marker {
  display: none;
}

.status-legend summary::after {
  content: '+';
  color: var(--text-subtle);
  font-family: var(--mono);
}

.status-legend[open] summary::after {
  content: '-';
}

.status-legend-list {
  display: grid;
  gap: 9px;
  padding: 2px 12px 12px;
}

.status-legend-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
}

.status-legend-copy {
  display: grid;
  gap: 2px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.secondary-details {
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  background: linear-gradient(165deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.005) 40%, transparent),
  var(--bg-panel);
  box-shadow: inset 0 1px 0 var(--panel-specular), 0 18px 40px -16px rgba(7, 11, 13, 0.65);
}

.secondary-details summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  list-style: none;
}

.secondary-details summary::-webkit-details-marker {
  display: none;
}

.secondary-details summary::after {
  content: '+';
  color: var(--text-subtle);
  font-family: var(--mono);
}

.secondary-details[open] summary::after {
  content: '-';
}

.secondary-details-body {
  padding: 2px 12px 12px;
}

.secondary-details-copy {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.5;
  margin: 0 0 12px;
}

.inline-saving {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-subtle);
  font-size: 11px;
  font-weight: 500;
}

.library-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 56px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 8px 9px;
  background: rgba(255, 255, 255, 0.02);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.14s ease, background 0.14s ease;
}

.library-row:hover,
.library-row--active {
  border-color: rgba(194, 161, 107, 0.26);
  background: rgba(194, 161, 107, 0.055);
}

.state-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-subtle);
}

.state-dot--verified {
  color: var(--status-success);
  background: rgba(55, 230, 138, 0.09);
}

.state-dot--pending {
  color: var(--status-info);
  background: rgba(48, 213, 200, 0.08);
}

.state-dot--stale {
  color: var(--status-warning);
  background: rgba(245, 165, 36, 0.09);
}

.state-dot--not_intercepted {
  color: var(--text-subtle);
  background: rgba(255, 255, 255, 0.045);
}

.state-dot--error {
  color: var(--status-danger);
  background: rgba(255, 92, 122, 0.09);
}

.library-row-main {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.library-row-name {
  color: var(--text-main);
  font-size: 12px;
  font-weight: 750;
  line-height: 1.2;
}

.library-row-path {
  color: var(--text-subtle);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-label {
  justify-self: end;
  max-width: 82px;
  font-size: 9px;
  font-weight: 750;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  line-height: 1.15;
  text-align: right;
}

.state-label--verified {
  color: var(--status-success);
}

.state-label--pending {
  color: var(--status-info);
}

.state-label--stale {
  color: var(--status-warning);
}

.state-label--not_intercepted {
  color: var(--text-subtle);
}

.state-label--error {
  color: var(--status-danger);
}

.resolution-panel {
  min-height: 460px;
}

.resolution-empty {
  min-height: 330px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  color: var(--text-subtle);
  font-size: 13px;
  text-align: center;
}

.resolution-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.advanced-mode-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  margin: 0 0 14px;
  padding: 12px;
  border: 1px solid rgba(245, 165, 36, 0.24);
  border-radius: 8px;
  background: rgba(245, 165, 36, 0.075);
}

.advanced-mode-panel .form-input {
  max-width: none;
}

.advanced-mode-kicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  margin: 0 0 8px;
  padding: 3px 7px;
  border: 1px solid rgba(245, 165, 36, 0.32);
  border-radius: 6px;
  color: var(--status-warning);
  background: rgba(245, 165, 36, 0.08);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.advanced-mode-exit {
  justify-self: end;
  margin-bottom: 9px;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .advanced-mode-panel {
    grid-template-columns: 1fr;
  }

  .advanced-mode-exit {
    justify-self: start;
    margin-bottom: 0;
  }
}

.resolution-name {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-main);
  margin: 0 0 4px;
}

.resolution-sub {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}

.power-switch-block {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.route-rails {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.access-step {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  padding: 11px 12px;
  border: 1px solid rgba(194, 161, 107, 0.14);
  border-radius: 8px;
  background: rgba(194, 161, 107, 0.045);
}

.access-config {
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.075);
}

.smb-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.smb-form-grid .form-input {
  max-width: none;
}

.access-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.access-config > .access-actions:first-child {
  margin-top: 0;
}

.access-step-main {
  display: grid;
  grid-template-columns: 24px 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 8px;
}

.access-step-main svg {
  color: var(--accent-secondary);
}

.step-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  background: rgba(194, 161, 107, 0.10);
  color: var(--accent-secondary);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
}

.access-step-copy {
  min-width: 0;
}

.access-step-title {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 750;
  margin: 0 0 2px;
}

.access-step-sub {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
  margin: 0;
}

.access-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-main);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .access-step-main {
    grid-template-columns: 24px 20px minmax(0, 1fr);
  }

  .access-toggle {
    grid-column: 3;
    justify-self: start;
  }

  .smb-form-grid {
    grid-template-columns: 1fr;
  }
}

.route-rail {
  border: 1px solid rgba(255, 255, 255, 0.075);
  border-radius: 8px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.025);
}

.route-rail--oppo {
  border-color: rgba(194, 161, 107, 0.16);
  background: rgba(194, 161, 107, 0.035);
}

.route-rail-label {
  font-size: 10px;
  font-weight: 800;
  color: var(--text-subtle);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 7px;
}

.route-value {
  color: var(--text-main);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.route-link {
  width: 1px;
  height: 22px;
  background: rgba(194, 161, 107, 0.28);
  margin-left: 24px;
}

.route-input-row {
  display: flex;
  gap: 9px;
  align-items: center;
}

.route-input {
  max-width: none;
}

@media (max-width: 680px) {
  .route-input-row,
  .resolution-actions {
    flex-direction: column;
    align-items: stretch;
  }
}

.folder-nav {
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  max-height: 220px;
  overflow-y: auto;
}

.folder-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.1s;
  font-family: var(--mono);
  background: none;
  border: none;
  text-align: left;
}

.folder-item:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-main);
}

.folder-up {
  display: inline-flex;
  width: 14px;
  justify-content: center;
  color: var(--text-subtle);
}

.folder-empty,
.folder-error,
.folder-loading {
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.5;
}

.folder-empty {
  color: var(--text-subtle);
}

.folder-error {
  color: var(--status-danger);
}

.folder-loading,
.compact-saving {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
}

.compact-saving {
  padding: 0;
  font-size: 11px;
}

.folder-loading-spinner {
  display: inline-block;
  width: 11px;
  height: 11px;
  border: 2px solid var(--panel-border);
  border-top-color: var(--text-muted);
  border-radius: 50%;
  animation: folder-spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes folder-spin {
  to {
    transform: rotate(360deg);
  }
}

.suggestion-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 11px 12px;
  border: 1px solid rgba(48, 213, 200, 0.16);
  border-radius: 8px;
  background: rgba(48, 213, 200, 0.055);
}

.suggestion-title {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 3px;
}

.suggestion-path {
  color: var(--text-main);
  font-size: 11px;
  margin: 0;
  overflow-wrap: anywhere;
}

.path-preview {
  background: rgba(127, 166, 181, 0.06);
  border: 1px solid rgba(127, 166, 181, 0.15);
  border-radius: 7px;
  padding: 10px 12px;
}

.preview-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-subtle);
  margin-bottom: 6px;
}

.preview-row {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  margin-bottom: 2px;
}

.preview-arrow {
  font-size: 11px;
  color: var(--text-subtle);
  padding-left: 52px;
  margin-bottom: 4px;
}

.preview-key {
  color: var(--text-subtle);
  font-size: 10px;
  min-width: 52px;
}

.preview-val {
  color: var(--text-main);
  font-size: 11px;
}

.verify-note {
  font-size: 13px;
  margin: 12px 0 0;
}

.verify-note--ok {
  color: var(--status-success);
}

.verify-note--stale {
  color: var(--status-warning);
}

.resolution-actions {
  display: flex;
  gap: 9px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 16px;
}

.btn-danger-inline {
  color: var(--status-danger);
  margin-left: auto;
}

.diag-inline {
  background: rgba(255, 92, 122, 0.06);
  border: 1px solid rgba(255, 92, 122, 0.2);
  border-radius: 7px;
  padding: 10px 14px;
}

.diag-inline-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-subtle);
  margin-bottom: 2px;
}

.diag-inline-reason {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0;
}

.diag-inline-suggestion {
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.5;
  margin: 0;
}

.library-filter-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px 14px;
}

.library-filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.network-mode {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border: 1px solid rgba(194, 161, 107, 0.12);
  border-radius: 8px;
  background: rgba(194, 161, 107, 0.045);
  margin-bottom: 14px;
}

.network-mode svg {
  color: var(--accent-secondary);
  margin-top: 1px;
}

.network-mode-label {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 750;
  margin: 0 0 2px;
}

.network-mode-copy {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
  margin: 0;
}

.smb-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(39, 174, 96, 0.07);
  border: 1px solid rgba(39, 174, 96, 0.18);
  border-radius: 7px;
}

.smb-status svg {
  color: var(--status-success);
  flex-shrink: 0;
}

.smb-status-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
  line-height: 1.3;
}

.mono {
  font-family: var(--mono);
}
</style>
