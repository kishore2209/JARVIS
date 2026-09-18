import type {
  RecognitionLike,
  SpeechRecognitionAdapter as SpeechRecognitionAdapterContract,
  SpeechRecognitionAdapterOptions,
  VoiceErrorCode,
  VoiceLanguage,
  VoiceState,
} from './types';

interface RecognitionWindow extends Window {
  SpeechRecognition?: new () => RecognitionLike;
  webkitSpeechRecognition?: new () => RecognitionLike;
}

function defaultFactory(): RecognitionLike | null {
  if (typeof window === 'undefined') return null;
  const recognitionWindow = window as RecognitionWindow;
  const Constructor = recognitionWindow.SpeechRecognition ?? recognitionWindow.webkitSpeechRecognition;
  return Constructor ? new Constructor() : null;
}

function mapError(error: string | undefined): VoiceErrorCode {
  if (error === 'not-allowed' || error === 'service-not-allowed') return 'MICROPHONE_PERMISSION_DENIED';
  if (error === 'no-speech') return 'VOICE_NO_SPEECH';
  if (error === 'aborted') return 'VOICE_ABORTED';
  return 'VOICE_RECOGNITION_ERROR';
}

export class BrowserSpeechRecognitionAdapter implements SpeechRecognitionAdapterContract {
  private recognition: RecognitionLike | null = null;
  private state: VoiceState = 'IDLE';
  private finalTranscript = '';
  onStart?: () => void;
  onInterimTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  onError?: (code: VoiceErrorCode) => void;
  onEnd?: () => void;

  constructor(private readonly options: SpeechRecognitionAdapterOptions = {}) {}

  isSupported(): boolean {
    return Boolean(this.options.createRecognition ? this.options.createRecognition() : defaultFactory());
  }

  getState(): VoiceState {
    return this.state;
  }

  async start(language: VoiceLanguage): Promise<void> {
    this.recognition = this.options.createRecognition ? this.options.createRecognition() : defaultFactory();
    if (!this.recognition) {
      this.state = 'UNSUPPORTED';
      this.onError?.('VOICE_INPUT_UNSUPPORTED');
      return;
    }
    this.finalTranscript = '';
    this.state = 'REQUESTING_PERMISSION';
    this.recognition.lang = language || 'en-IN';
    this.recognition.interimResults = true;
    this.recognition.continuous = false;
    this.recognition.onstart = () => {
      this.state = 'LISTENING';
      this.onStart?.();
    };
    this.recognition.onresult = event => {
      let interim = '';
      let finalText = '';
      for (let index = event.resultIndex ?? 0; index < event.results.length; index += 1) {
        const text = event.results[index]?.[0]?.transcript ?? '';
        if ((event.results[index] as ArrayLike<{ isFinal?: boolean }> & { isFinal?: boolean }).isFinal) finalText += text;
        else interim += text;
      }
      if (finalText) {
        this.finalTranscript += finalText;
        this.state = 'TRANSCRIPT_READY';
        this.onFinalTranscript?.(this.finalTranscript.trim());
      } else if (interim) {
        this.onInterimTranscript?.(interim);
      }
    };
    this.recognition.onerror = event => {
      this.state = 'ERROR';
      this.onError?.(mapError(event.error));
    };
    this.recognition.onend = () => {
      if (this.state === 'LISTENING' || this.state === 'REQUESTING_PERMISSION') this.state = 'IDLE';
      this.onEnd?.();
    };
    try {
      this.recognition.start();
    } catch {
      this.state = 'ERROR';
      this.onError?.('VOICE_RECOGNITION_ERROR');
    }
  }

  stop(): void {
    if (!this.recognition) return;
    this.recognition.stop();
    this.state = 'IDLE';
  }
}
