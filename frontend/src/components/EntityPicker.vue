<template>
  <div class="entity-picker">
    <input
        v-if="showFilter"
        v-model="filter"
        :disabled="disabled"
        :placeholder="filterPlaceholder"
        class="form-input mb-2"
        type="search"
    />
    <div v-if="options.length || noneLabel" :class="['entity-picker-list', disabled && 'is-disabled']">
      <label v-if="!multiple && noneLabel" class="entity-picker-item">
        <input
            :checked="!modelValue"
            :disabled="disabled"
            :name="groupName"
            type="radio"
            @change="emit('update:modelValue', '')"
        />
        <span class="entity-picker-name">{{ noneLabel }}</span>
      </label>
      <label v-for="entity in options" :key="entity.entity_id" class="entity-picker-item">
        <input
            :aria-label="entity.name"
            :checked="isSelected(entity.entity_id)"
            :disabled="disabled"
            :name="multiple ? undefined : groupName"
            :type="multiple ? 'checkbox' : 'radio'"
            @change="select(entity.entity_id)"
        />
        <span class="entity-picker-name">
          {{ entity.name }}
          <span v-if="entity.state" :class="['entity-picker-state', `is-${entity.state}`]">{{ entity.state }}</span>
        </span>
        <span class="entity-picker-id">{{ entity.entity_id }}</span>
      </label>
    </div>
    <p v-if="!entities.length && emptyText" class="section-hint mt-2">{{ emptyText }}</p>
  </div>
</template>

<script setup>
import {computed, ref} from 'vue'

// Picks Home Assistant entities from a filterable list: several (checkboxes,
// modelValue is an array of entity ids) or one (radios, modelValue is an
// entity id string, '' for none).
const props = defineProps({
  entities: {type: Array, default: () => []},
  modelValue: {type: [Array, String], default: () => []},
  multiple: {type: Boolean, default: true},
  filterPlaceholder: {type: String, default: ''},
  emptyText: {type: String, default: ''},
  noneLabel: {type: String, default: ''},
  disabled: {type: Boolean, default: false},
  filterThreshold: {type: Number, default: 8},
})

const emit = defineEmits(['update:modelValue'])

// Radios of one picker must share a name that no other picker uses.
const groupName = `entity-picker-${Math.random().toString(36).slice(2, 10)}`
const filter = ref('')

const selectedIds = computed(() => {
  if (props.multiple) return props.modelValue || []
  return props.modelValue ? [props.modelValue] : []
})

// Detected entities plus any stored id Home Assistant did not report
// (renamed/unavailable), so a saved selection is never silently dropped.
const allOptions = computed(() => {
  const known = new Map(props.entities.map((entity) => [entity.entity_id, entity]))
  for (const entityId of selectedIds.value) {
    if (!known.has(entityId)) known.set(entityId, {entity_id: entityId, name: entityId, state: ''})
  }
  return [...known.values()]
})

const showFilter = computed(() => allOptions.value.length > props.filterThreshold)

const options = computed(() => {
  const text = filter.value.trim().toLowerCase()
  if (!text) return allOptions.value
  return allOptions.value.filter((entity) =>
      entity.entity_id.toLowerCase().includes(text) || String(entity.name).toLowerCase().includes(text))
})

function isSelected(entityId) {
  return selectedIds.value.includes(entityId)
}

function select(entityId) {
  if (!props.multiple) {
    emit('update:modelValue', entityId)
    return
  }
  const selected = new Set(props.modelValue || [])
  if (selected.has(entityId)) selected.delete(entityId)
  else selected.add(entityId)
  emit('update:modelValue', [...selected])
}
</script>

<style scoped>
.entity-picker-list {
  display: grid;
  gap: 4px;
  max-height: 240px;
  overflow-y: auto;
  padding: 6px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.075);
  background: rgba(7, 11, 13, 0.32);
}

.entity-picker-list.is-disabled {
  opacity: 0.55;
}

.entity-picker-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: 8px;
  align-items: center;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}

.entity-picker-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.entity-picker-item input {
  grid-row: span 2;
}

.entity-picker-name {
  color: var(--text-main);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.entity-picker-state {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.entity-picker-state.is-on {
  color: var(--status-success);
  border-color: currentColor;
}

.entity-picker-id {
  color: var(--text-muted);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}
</style>
