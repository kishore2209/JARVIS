import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {VoicePanel} from './VoicePanel';
import {BrowserSpeechRecognitionAdapter} from '../voice/SpeechRecognitionAdapter';
import {BrowserSpeechSynthesisAdapter,safeSpeechText} from '../voice/SpeechSynthesisAdapter';
import type {RecognitionLike,RecognitionResultEvent,SpeechRecognitionAdapter,SpeechSynthesisAdapter,SpeechSynthesisLike,SpeechSynthesisUtteranceLike,VoiceLanguage,VoiceState} from '../voice/types';

afterEach(cleanup);

class FakeRecognition implements RecognitionLike {
  lang = '';
  interimResults = false;
  continuous = false;
  started = 0;
  stopped = 0;
  onstart: (() => void) | null = null;
  onresult: ((event: RecognitionResultEvent) => void) | null = null;
  onerror: ((event: {error?: string}) => void) | null = null;
  onend: (() => void) | null = null;
  start() { this.started += 1; this.onstart?.(); }
  stop() { this.stopped += 1; this.onend?.(); }
  emit(text: string, isFinal: boolean) { this.onresult?.({results: [{0: {transcript: text}, length: 1, isFinal}] as unknown as ArrayLike<ArrayLike<{transcript: string}> & {isFinal?: boolean}>, resultIndex: 0}); }
}

class FakeRecognitionAdapter implements SpeechRecognitionAdapter {
  state: VoiceState = 'IDLE';
  language: VoiceLanguage = '';
  starts = 0;
  stops = 0;
  onStart?: () => void;
  onInterimTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  onError?: (code: 'VOICE_INPUT_UNSUPPORTED' | 'MICROPHONE_PERMISSION_DENIED' | 'VOICE_RECOGNITION_ERROR' | 'VOICE_NO_SPEECH' | 'VOICE_ABORTED' | 'VOICE_TTS_UNSUPPORTED' | 'VOICE_TTS_ERROR') => void;
  onEnd?: () => void;
  isSupported() { return true; }
  getState() { return this.state; }
  async start(language: VoiceLanguage) { this.language = language; this.starts += 1; this.state = 'LISTENING'; this.onStart?.(); }
  stop() { this.stops += 1; this.state = 'IDLE'; this.onEnd?.(); }
  final(text: string) { this.state = 'TRANSCRIPT_READY'; this.onFinalTranscript?.(text); }
  interim(text: string) { this.onInterimTranscript?.(text); }
  fail(code: Parameters<NonNullable<SpeechRecognitionAdapter['onError']>>[0]) { this.onError?.(code); }
}

class FakeSynthesisAdapter implements SpeechSynthesisAdapter {
  supported = true;
  speaking = false;
  spoken: Array<{text: string; language: VoiceLanguage}> = [];
  stopped = 0;
  isSupported() { return this.supported; }
  isSpeaking() { return this.speaking; }
  speak(text: string, language: VoiceLanguage) { this.speaking = true; this.spoken.push({text, language}); }
  stop() { this.speaking = false; this.stopped += 1; }
}

function renderVoice(overrides: Partial<{recognition: FakeRecognitionAdapter; synthesis: FakeSynthesisAdapter}> = {}, submitChat = vi.fn(async () => ({message: 'Safe response'}))) {
  const recognition = overrides.recognition ?? new FakeRecognitionAdapter();
  const synthesis = overrides.synthesis ?? new FakeSynthesisAdapter();
  render(<VoicePanel submitChat={submitChat} recognition={recognition} synthesis={synthesis}/>);
  return {recognition, synthesis, submitChat};
}

describe('VoicePanel', () => {
  it('shows explicit controls, capabilities, labels, and no auto-submit', async () => {
    const {recognition, submitChat} = renderVoice();
    expect(screen.getByRole('button', {name: 'Start Listening'})).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Stop Listening'})).toBeTruthy();
    expect(screen.getByLabelText('Voice language')).toBeTruthy();
    expect(screen.getByLabelText('Voice transcript')).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Send Transcript'})).toBeTruthy();
    expect(screen.getByLabelText('Speak Responses')).toBeTruthy();
    expect(screen.getByRole('button', {name: 'Stop Speaking'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.final('Buy RELIANCE live');
    await waitFor(() => expect(screen.getByDisplayValue('Buy RELIANCE live')).toBeTruthy());
    expect(submitChat).not.toHaveBeenCalled();
  });

  it('supports start, stop, interim/final transcript, editing, clear, and language selection', async () => {
    const {recognition} = renderVoice();
    fireEvent.change(screen.getByLabelText('Voice language'), {target: {value: 'te-IN'}});
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    expect(recognition.starts).toBe(1);
    await waitFor(() => expect(screen.getByText('Microphone: LISTENING')).toBeTruthy());
    recognition.interim('analyse reli');
    await waitFor(() => expect(screen.getByText('Interim: analyse reli')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Stop Listening'}));
    expect(recognition.stops).toBe(1);
    recognition.final('analyse reliance');
    await waitFor(() => expect(screen.getByDisplayValue('analyse reliance')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Voice transcript'), {target: {value: 'Analyse RELIANCE'}});
    fireEvent.click(screen.getByRole('button', {name: 'Clear Transcript'}));
    expect(screen.getByDisplayValue('')).toBeTruthy();
    expect(recognition.language).toBe('te-IN');
    await waitFor(() => expect(screen.getByText('Microphone: IDLE')).toBeTruthy());
  });

  it('sends an exact transcript once, including Telugu and mixed-language text', async () => {
    const {recognition, submitChat} = renderVoice();
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.final('RELIANCE analysis cheyyi');
    await waitFor(() => expect(screen.getByDisplayValue('RELIANCE analysis cheyyi')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Send Transcript'}));
    await waitFor(() => expect(submitChat).toHaveBeenCalledTimes(1));
    expect(submitChat).toHaveBeenCalledWith('RELIANCE analysis cheyyi', 'en-IN');
    fireEvent.change(screen.getByLabelText('Voice transcript'), {target: {value: 'నా portfolio చూపించు'}});
    fireEvent.click(screen.getByRole('button', {name: 'Send Transcript'}));
    await waitFor(() => expect(submitChat).toHaveBeenCalledTimes(2));
    expect(submitChat).toHaveBeenLastCalledWith('నా portfolio చూపించు', 'en-IN');
  });

  it('keeps voice safety boundaries: text only, no Paper authorization or direct endpoint', async () => {
    const {recognition, submitChat} = renderVoice();
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.final('Paper buy RELIANCE at 1200 stop 1180 target 1240 yes');
    await waitFor(() => expect(screen.getByDisplayValue('Paper buy RELIANCE at 1200 stop 1180 target 1240 yes')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Send Transcript'}));
    await waitFor(() => expect(submitChat).toHaveBeenCalledTimes(1));
    expect(submitChat).toHaveBeenCalledWith(expect.stringContaining('Paper buy RELIANCE'), 'en-IN');
    expect(screen.queryByLabelText(/authorize this PAPER trade/i)).toBeNull();
    expect(submitChat.mock.calls.flat().join(' ')).not.toContain('/api/v1/paper/execute');
  });

  it('handles permission denied, no speech, recognition errors, and unsupported input', async () => {
    const recognition = new FakeRecognitionAdapter();
    renderVoice({recognition});
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.fail('MICROPHONE_PERMISSION_DENIED');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('MICROPHONE_PERMISSION_DENIED'));
    recognition.fail('VOICE_NO_SPEECH');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('VOICE_NO_SPEECH'));
    recognition.fail('VOICE_RECOGNITION_ERROR');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('VOICE_RECOGNITION_ERROR'));
  });

  it('speaks only the safe assistant message, supports Telugu, stops, and prevents overlap', async () => {
    const synthesis = new FakeSynthesisAdapter();
    const submitChat = vi.fn(async () => ({message: 'Analysis complete', structured_result: {secret: 'hidden', huge: 'not spoken'}}));
    const {recognition} = renderVoice({synthesis}, submitChat);
    fireEvent.change(screen.getByLabelText('Voice language'), {target: {value: 'te-IN'}});
    fireEvent.click(screen.getByLabelText('Speak Responses'));
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.final('Analyse RELIANCE');
    await waitFor(() => expect(screen.getByDisplayValue('Analyse RELIANCE')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Send Transcript'}));
    await waitFor(() => expect(synthesis.spoken).toHaveLength(1));
    expect(synthesis.spoken[0]).toEqual({text: 'Analysis complete', language: 'te-IN'});
    expect(synthesis.spoken[0].text).not.toContain('hidden');
    fireEvent.click(screen.getByRole('button', {name: 'Stop Speaking'}));
    expect(synthesis.stopped).toBeGreaterThan(0);
  });

  it('handles unsupported TTS without failing chat', async () => {
    const synthesis = new FakeSynthesisAdapter();
    synthesis.supported = false;
    const {recognition, submitChat} = renderVoice({synthesis});
    fireEvent.click(screen.getByLabelText('Speak Responses'));
    fireEvent.click(screen.getByRole('button', {name: 'Start Listening'}));
    recognition.final('hello');
    await waitFor(() => expect(screen.getByDisplayValue('hello')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', {name: 'Send Transcript'}));
    await waitFor(() => expect(submitChat).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('VOICE_TTS_UNSUPPORTED'));
  });
});

describe('Speech adapters', () => {
  it('recognizes English/Telugu settings, final results, stop, permission, no speech, and unsupported input', async () => {
    const fake = new FakeRecognition();
    const adapter = new BrowserSpeechRecognitionAdapter({createRecognition: () => fake});
    const final = vi.fn();
    const errors = vi.fn();
    adapter.onFinalTranscript = final;
    adapter.onError = errors;
    expect(adapter.isSupported()).toBe(true);
    await adapter.start('te-IN');
    expect(fake.lang).toBe('te-IN');
    expect(fake.interimResults).toBe(true);
    fake.emit('నా portfolio', true);
    expect(final).toHaveBeenCalledWith('నా portfolio');
    adapter.stop();
    expect(fake.stopped).toBe(1);
    fake.onerror?.({error: 'not-allowed'});
    fake.onerror?.({error: 'no-speech'});
    expect(errors).toHaveBeenNthCalledWith(1, 'MICROPHONE_PERMISSION_DENIED');
    expect(errors).toHaveBeenNthCalledWith(2, 'VOICE_NO_SPEECH');
    const unsupported = new BrowserSpeechRecognitionAdapter({createRecognition: () => null});
    const unsupportedError = vi.fn();
    unsupported.onError = unsupportedError;
    await unsupported.start('en-IN');
    expect(unsupportedError).toHaveBeenCalledWith('VOICE_INPUT_UNSUPPORTED');
  });

  it('does not persist audio and synthesis cancels overlapping speech', () => {
    const utterances: SpeechSynthesisUtteranceLike[] = [];
    const synthesis: SpeechSynthesisLike = {speaking: true, cancel: vi.fn(), speak: vi.fn(utterance => utterances.push(utterance))};
    const adapter = new BrowserSpeechSynthesisAdapter({synthesis, utteranceFactory: text => ({text, lang: '', onstart: null, onend: null, onerror: null})});
    adapter.speak('Safe response', 'en-IN');
    adapter.speak('Second response', 'te-IN');
    expect(synthesis.cancel).toHaveBeenCalledTimes(2);
    expect(utterances[1]).toMatchObject({text: 'Second response', lang: 'te-IN'});
    adapter.stop();
    expect(synthesis.cancel).toHaveBeenCalledTimes(3);
    expect(safeSpeechText({message: 'message\nonly', structured_result: {token: 'secret'}})).toBe('message only');
    expect(safeSpeechText({structured_result: {token: 'secret'}})).toBe('');
  });

  it('maps synthesis errors to a safe callback', () => {
    const utterances: SpeechSynthesisUtteranceLike[] = [];
    const synthesis: SpeechSynthesisLike = {speaking: false, cancel: vi.fn(), speak: vi.fn(utterance => utterances.push(utterance))};
    const adapter = new BrowserSpeechSynthesisAdapter({synthesis, utteranceFactory: text => ({text, lang: '', onstart: null, onend: null, onerror: null})});
    const error = vi.fn();
    adapter.onError = error;
    adapter.speak('Safe response', 'en-IN');
    utterances[0].onerror?.();
    expect(error).toHaveBeenCalledTimes(1);
  });
});
