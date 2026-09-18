export type VoiceLanguage = 'en-IN' | 'te-IN' | '';

export type VoiceState =
  | 'IDLE'
  | 'REQUESTING_PERMISSION'
  | 'LISTENING'
  | 'TRANSCRIPT_READY'
  | 'PROCESSING'
  | 'SPEAKING'
  | 'ERROR'
  | 'UNSUPPORTED';

export type VoiceErrorCode =
  | 'VOICE_INPUT_UNSUPPORTED'
  | 'MICROPHONE_PERMISSION_DENIED'
  | 'VOICE_RECOGNITION_ERROR'
  | 'VOICE_NO_SPEECH'
  | 'VOICE_ABORTED'
  | 'VOICE_TTS_UNSUPPORTED'
  | 'VOICE_TTS_ERROR';

export interface RecognitionResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal?: boolean }>;
  resultIndex?: number;
}

export interface RecognitionErrorEvent {
  error?: string;
}

export interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  abort?(): void;
  onstart: (() => void) | null;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

export interface SpeechRecognitionAdapterOptions {
  createRecognition?: () => RecognitionLike | null;
}

export interface SpeechRecognitionAdapter {
  start(language: VoiceLanguage): Promise<void>;
  stop(): void;
  isSupported(): boolean;
  getState(): VoiceState;
  onStart?: () => void;
  onInterimTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  onError?: (code: VoiceErrorCode) => void;
  onEnd?: () => void;
}

export interface SpeechSynthesisAdapter {
  speak(text: string, language: VoiceLanguage): void;
  stop(): void;
  isSupported(): boolean;
  isSpeaking(): boolean;
  onStart?: () => void;
  onEnd?: () => void;
  onError?: () => void;
}

export interface SpeechSynthesisAdapterOptions {
  synthesis?: SpeechSynthesisLike | null;
  utteranceFactory?: (text: string) => SpeechSynthesisUtteranceLike;
}

export interface SpeechSynthesisUtteranceLike {
  text: string;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

export interface SpeechSynthesisLike {
  speaking: boolean;
  cancel(): void;
  speak(utterance: SpeechSynthesisUtteranceLike): void;
}
