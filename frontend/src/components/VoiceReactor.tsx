import type { VoiceState } from '../voice/types';

const captions: Record<VoiceState, string> = {
  IDLE: 'Ready when you are', REQUESTING_PERMISSION: 'Waiting for microphone permission',
  LISTENING: 'Listening to you', TRANSCRIPT_READY: 'Review your words, then send',
  PROCESSING: 'Working on your request', SPEAKING: 'Speaking the response',
  ERROR: 'Check the voice controls below', UNSUPPORTED: 'Use text on this browser',
};

export function VoiceReactor({state}: {state: VoiceState}) {
  return <div className={`voice-reactor state-${state.toLowerCase()}`}>
    <div className="reactor-orbit" aria-hidden="true"><div className="reactor-core">J</div></div>
    <div><small>J.A.R.V.I.S / VOICE</small><h3>{captions[state]}</h3>
      <p>English · తెలుగు</p><small>Review before sending. Voice never authorizes a trade.</small>
    </div>
  </div>;
}
