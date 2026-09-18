import { useEffect, useRef, useState } from 'react';
import { BrowserSpeechRecognitionAdapter } from '../voice/SpeechRecognitionAdapter';
import { BrowserSpeechSynthesisAdapter, safeSpeechText } from '../voice/SpeechSynthesisAdapter';
import type { SpeechRecognitionAdapter, SpeechSynthesisAdapter, VoiceErrorCode, VoiceLanguage, VoiceState } from '../voice/types';

type ResponseData = Record<string, unknown>;

interface VoicePanelProps {
  submitChat: (text: string, language: VoiceLanguage) => Promise<ResponseData | undefined>;
  recognition?: SpeechRecognitionAdapter;
  synthesis?: SpeechSynthesisAdapter;
}

const errorLabels: Record<VoiceErrorCode, string> = {
  VOICE_INPUT_UNSUPPORTED: 'VOICE_INPUT_UNAVAILABLE',
  MICROPHONE_PERMISSION_DENIED: 'MICROPHONE_PERMISSION_DENIED',
  VOICE_RECOGNITION_ERROR: 'VOICE_RECOGNITION_ERROR',
  VOICE_NO_SPEECH: 'VOICE_NO_SPEECH',
  VOICE_ABORTED: 'VOICE_ABORTED',
  VOICE_TTS_UNSUPPORTED: 'VOICE_TTS_UNSUPPORTED',
  VOICE_TTS_ERROR: 'VOICE_TTS_ERROR',
};

export function VoicePanel({submitChat, recognition: injectedRecognition, synthesis: injectedSynthesis}: VoicePanelProps) {
  const [recognition] = useState<SpeechRecognitionAdapter>(() => injectedRecognition ?? new BrowserSpeechRecognitionAdapter());
  const [synthesis] = useState<SpeechSynthesisAdapter>(() => injectedSynthesis ?? new BrowserSpeechSynthesisAdapter());
  const [language, setLanguage] = useState<VoiceLanguage>('en-IN');
  const [state, setState] = useState<VoiceState>(recognition.isSupported() ? 'IDLE' : 'UNSUPPORTED');
  const [transcript, setTranscript] = useState('');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState('');
  const [speakResponses, setSpeakResponses] = useState(false);
  const speakingRef = useRef(false);

  useEffect(() => {
    recognition.onStart = () => { setError(''); setInterim(''); setState('LISTENING'); synthesis.stop(); };
    recognition.onInterimTranscript = value => setInterim(value);
    recognition.onFinalTranscript = value => { setTranscript(value); setInterim(''); setState('TRANSCRIPT_READY'); };
    recognition.onError = code => { setInterim(''); setError(errorLabels[code]); setState(code === 'VOICE_INPUT_UNSUPPORTED' ? 'UNSUPPORTED' : 'ERROR'); };
    recognition.onEnd = () => setState(current => current === 'LISTENING' ? 'IDLE' : current);
    synthesis.onStart = () => { speakingRef.current = true; setState('SPEAKING'); };
    synthesis.onEnd = () => { speakingRef.current = false; setState(current => current === 'SPEAKING' ? 'IDLE' : current); };
    synthesis.onError = () => { speakingRef.current = false; setError('VOICE_TTS_ERROR'); setState('ERROR'); };
    return () => { recognition.stop(); synthesis.stop(); };
  }, [recognition, synthesis]);

  const startListening = async () => {
    setError('');
    setInterim('');
    setState('REQUESTING_PERMISSION');
    await recognition.start(language);
  };

  const stopListening = () => {
    recognition.stop();
    setInterim('');
    setState('IDLE');
  };

  const sendTranscript = async () => {
    const text = transcript.trim();
    if (!text) return;
    setState('PROCESSING');
    const response = await submitChat(text, language);
    if (speakResponses) {
      const message = safeSpeechText(response);
      if (!message || !synthesis.isSupported()) {
        setError(!synthesis.isSupported() ? 'VOICE_TTS_UNSUPPORTED' : '');
        setState(!synthesis.isSupported() ? 'ERROR' : 'IDLE');
        return;
      }
      speakingRef.current = true;
      synthesis.speak(message, language);
      setState('SPEAKING');
    } else {
      setState('IDLE');
    }
  };

  const stopSpeaking = () => {
    synthesis.stop();
    speakingRef.current = false;
    setState(current => current === 'SPEAKING' ? 'IDLE' : current);
  };

  return <div className="panel voice-panel" aria-label="Voice controls">
    <h3>Voice Interface</h3>
    <p role="status">Microphone: {state}</p>
    <p>Voice Input: {recognition.isSupported() ? 'AVAILABLE' : 'UNAVAILABLE'} | Voice Output: {synthesis.isSupported() ? 'AVAILABLE' : 'UNAVAILABLE'}</p>
    <label>Language<select aria-label="Voice language" value={language} onChange={event => setLanguage(event.target.value as VoiceLanguage)}><option value="en-IN">English</option><option value="te-IN">Telugu</option><option value="">Auto / browser default</option></select></label>
    <div className="actions"><button type="button" onClick={startListening} disabled={!recognition.isSupported() || state === 'LISTENING' || state === 'PROCESSING'}>Start Listening</button><button type="button" onClick={stopListening} disabled={state !== 'LISTENING' && state !== 'REQUESTING_PERMISSION'}>Stop Listening</button></div>
    {interim && <p aria-live="polite">Interim: {interim}</p>}
    <label>Transcript<textarea aria-label="Voice transcript" value={transcript} onChange={event => setTranscript(event.target.value)} rows={3}/></label>
    <div className="actions"><button type="button" onClick={sendTranscript} disabled={!transcript.trim() || state === 'PROCESSING'}>Send Transcript</button><button type="button" onClick={() => { setTranscript(''); setInterim(''); setError(''); setState('IDLE'); }}>Clear Transcript</button></div>
    <label className="voice-toggle"><input type="checkbox" checked={speakResponses} onChange={event => setSpeakResponses(event.target.checked)}/>Speak Responses</label>
    <button type="button" onClick={stopSpeaking} disabled={!speakingRef.current && !synthesis.isSpeaking()}>Stop Speaking</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
