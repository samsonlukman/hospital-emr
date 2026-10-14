/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BAHMNI_ORIGIN: string;
  readonly VITE_ATTENDANCE_TERMINAL_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
