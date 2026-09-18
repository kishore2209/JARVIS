import type {
  SpeechSynthesisAdapter as SpeechSynthesisAdapterContract,
  SpeechSynthesisAdapterOptions,
  SpeechSynthesisLike,
  SpeechSynthesisUtteranceLike,
  VoiceLanguage,
} from './types';

function defaultSynthesis(): SpeechSynthesisLike | null {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null;
  return window.speechSynthesis as unknown as SpeechSynthesisLike;
}

function defaultUtterance(text: string): SpeechSynthesisUtteranceLike {
  return new SpeechSynthesisUtterance(text) as unknown as SpeechSynthesisUtteranceLike;
}

export function safeSpeechText(value: unknown): string {
  if (!value || typeof value !== 'object') return typeof value === 'string' ? value : '';
  const message = (value as { message?: unknown }).message;
  if (typeof message !== 'string') return '';
  return message.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 500);
}

export class BrowserSpeechSynthesisAdapter implements SpeechSynthesisAdapterContract {
  private readonly synthesis: SpeechSynthesisLike | null;
  private readonly utteranceFactory: (text: string) => SpeechSynthesisUtteranceLike;

  constructor(options: SpeechSynthesisAdapterOptions = {}) {
    this.synthesis = options.synthesis === undefined ? defaultSynthesis() : options.synthesis;
    this.utteranceFactory = options.utteranceFactory ?? defaultUtterance;
  }

  onStart?: () => void;
  onEnd?: () => void;
  onError?: () => void;

  isSupported(): boolean {
    return Boolean(this.synthesis);
  }

  isSpeaking(): boolean {
    return Boolean(this.synthesis?.speaking);
  }

  speak(text: string, language: VoiceLanguage): void {
    if (!this.synthesis || !text.trim()) return;
    this.synthesis.cancel();
    const utterance = this.utteranceFactory(text.trim());
    utterance.lang = language || 'en-IN';
    utterance.onstart = () => this.onStart?.();
    utterance.onend = () => this.onEnd?.();
    utterance.onerror = () => this.onError?.();
    this.synthesis.speak(utterance);
  }

  stop(): void {
    this.synthesis?.cancel();
  }
}
