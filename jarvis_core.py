class JarvisCore:
	def __init__(self):
		self.name = "J.A.R.V.I.S"
		self.status = "ONLINE"

	def process_command(self, command):
		command = command.lower().strip()

		if command in ["hello", "hi", "hey"]:
			return "Hello. J.A.R.V.I.S is online."

		if "status" in command:
			return f"{self.name} is {self.status}."

		if "who are you" in command:
			return "I am J.A.R.V.I.S, your personal AI assistant."

		if "exit" in command or "quit" in command:
			return "Goodbye."

		return "I understand your command, but this capability is not implemented yet."


if __name__ == "__main__":
	jarvis = JarvisCore()

	print("================================")
	print("       J.A.R.V.I.S CORE")
	print("================================")
	print("Status: ONLINE")
	print("Type 'exit' to stop.\n")

	while True:
		command = input("You: ")

		response = jarvis.process_command(command)

		print(f"JARVIS: {response}")

		if command.lower().strip() in ["exit", "quit"]:
			break
