{{/*
Common labels applied to every resource.
*/}}
{{- define "nexusai.labels" -}}
app.kubernetes.io/name: nexusai
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/*
Container image reference; a digest takes precedence over the tag.
*/}}
{{- define "nexusai.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}
{{- end }}

{{/*
Name of the PersistentVolumeClaim holding SQLite databases and the API key store.
*/}}
{{- define "nexusai.dataClaimName" -}}
{{- default (printf "%s-data" .Release.Name) .Values.persistence.existingClaim -}}
{{- end }}

{{/*
Environment shared by every NexusAI container.
Chart-derived storage paths come first and are skipped when the same name is set in
`env` or `secretEnv`, so a container never receives a duplicate variable.
*/}}
{{- define "nexusai.env" -}}
{{- $mount := .Values.persistence.mountPath -}}
{{- $derived := dict
      "NEXUSAI_EXECUTION_DB" (printf "%s/execution.db" $mount)
      "NEXUSAI_COORDINATOR_DB" (printf "%s/coordinator.db" $mount)
      "NEXUSAI_KEY_STORAGE_PATH" (printf "%s/api_keys.json" $mount)
      "NEXUSAI_REPLICAS" (toString .Values.replicaCount.controlPlane)
      "TMPDIR" "/tmp" -}}
{{- range $name, $value := $derived }}
{{- if not (or (hasKey $.Values.env $name) (hasKey $.Values.secretEnv $name)) }}
- name: {{ $name }}
  value: {{ $value | quote }}
{{- end }}
{{- end }}
{{- if not (or (hasKey .Values.env "NEXUSAI_WORKER_ID") (hasKey .Values.secretEnv "NEXUSAI_WORKER_ID")) }}
- name: NEXUSAI_WORKER_ID
  valueFrom:
    fieldRef:
      fieldPath: metadata.name
{{- end }}
{{- range $name, $key := .Values.secretEnv }}
{{- if not (hasKey $.Values.env $name) }}
- name: {{ $name }}
  valueFrom:
    secretKeyRef:
      name: {{ $.Values.secrets.name }}
      key: {{ $key }}
      {{- if has $name $.Values.secrets.optionalKeys }}
      optional: true
      {{- end }}
{{- end }}
{{- end }}
{{- range $name, $value := .Values.env }}
- name: {{ $name }}
  {{- if kindIs "map" $value }}
  {{- toYaml $value | nindent 2 }}
  {{- else }}
  value: {{ $value | quote }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Writable mounts required under readOnlyRootFilesystem.
*/}}
{{- define "nexusai.volumeMounts" -}}
- name: data
  mountPath: {{ .Values.persistence.mountPath }}
- name: tmp
  mountPath: /tmp
- name: logs
  mountPath: /app/logs
{{- end }}

{{- define "nexusai.volumes" -}}
- name: data
  {{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "nexusai.dataClaimName" . }}
  {{- else }}
  emptyDir: {}
  {{- end }}
- name: tmp
  emptyDir:
    sizeLimit: {{ .Values.tmpSizeLimit }}
- name: logs
  emptyDir:
    sizeLimit: {{ .Values.logsSizeLimit }}
{{- end }}
