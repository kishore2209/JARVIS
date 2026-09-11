import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import pyttsx3
import time

# 1. Record Audio
samplerate = 16000
duration = 5
input_device = sd.default.device[0]
if input_device is None or input_device < 0:
	raise RuntimeError("No microphone is selected. Check Windows microphone permissions and input devices.")

input_devices = [
	(index, device["name"])
	for index, device in enumerate(sd.query_devices())
	if device["max_input_channels"] > 0
]
print("Available microphones:")
for index, name in input_devices:
	marker = " (default)" if index == input_device else ""
	print(f"  {index}: {name}{marker}")

choice = input("Enter microphone number, or press Enter for the default: ").strip()
if choice:
	try:
		input_device = int(choice)
	except ValueError as error:
		raise ValueError("Microphone number must be an integer.") from error

device_info = sd.query_devices(input_device, "input")
print(f"Using microphone: {device_info['name']}")
sd.check_input_settings(
	device=input_device,
	channels=1,
	dtype="int16",
	samplerate=samplerate,
)

print(f"Get ready. Recording starts in 3 seconds and lasts {duration} seconds.")
for seconds_left in range(3, 0, -1):
	print(f"{seconds_left}...")
	time.sleep(1)
print("Speak now!")

recording = sd.rec(
	int(duration * samplerate),
	samplerate=samplerate,
	channels=1,
	dtype="int16",
	device=input_device,
)
sd.wait()
print("Recording complete!")

# 2. Convert to float32 for Whisper (normalize)
audio_float = recording.flatten().astype(np.float32) / 32768.0
peak = float(np.max(np.abs(audio_float)))
rms = float(np.sqrt(np.mean(np.square(audio_float))))
print(f"Microphone signal: peak={peak:.4f}, RMS={rms:.4f}")
if peak < 0.01:
	print("Warning: the recording is nearly silent. Check the microphone mute switch and Windows input permissions.")

# 3. Transcribe Speech to Text
print("Processing audio...")
model = WhisperModel("tiny", device="cpu", compute_type="int8")
segments, info = model.transcribe(
	audio_float,
	beam_size=5,
	language="en",
	temperature=0,
	condition_on_previous_text=False,
)

text = "".join(segment.text for segment in segments)
print(f"You said: {text.strip()}")

# 4. Text to Speech Response
if text.strip():
	print("Jarvis Speaking...")
	engine = pyttsx3.init()
	engine.setProperty("rate", 150)  # Speed of speech
	engine.say(text)
	engine.runAndWait()
else:
	print("No speech detected. Try speaking louder!")

print("Task Complete!")