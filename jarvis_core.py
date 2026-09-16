from core.ai_brain import AIBrain
from memory.memory_manager import MemoryManager


class JarvisCore:
    def __init__(self):
        self.name = "J.A.R.V.I.S"
        self.status = "ONLINE"
        self.brain = AIBrain()
        self.memory = MemoryManager()

    def process_command(self, command):
        result = self.brain.understand(command)
        intent = result["intent"]

        if intent == "greeting":
            return "Hello. J.A.R.V.I.S is online."

        if intent == "system_status":
            return f"{self.name} is {self.status}."

        if intent == "identity":
            return "I am J.A.R.V.I.S, your personal AI assistant."

        if intent == "market_analysis":
            return "Market analysis capability is connected to the AI Brain."

        if "my name is " in command.lower():
            name = command.lower().split("my name is ", 1)[1].strip()
            if name:
                self.memory.remember("name", name.title())
                return f"I'll remember that. Your name is {name.title()}."

        if "what is my name" in command.lower():
            name = self.memory.recall("name")
            if name:
                return f"Your name is {name}."
            return "I don't know your name yet."

        if intent == "exit":
            return "Goodbye."

        return "I understand your command, but this capability is not implemented yet."


if __name__ == "__main__":
    jarvis = JarvisCore()
    print("================================")
    print("       J.A.R.V.I.S CORE")
    print("================================")
    print("Status: ONLINE")
    print("AI Brain: CONNECTED")
    print("Memory: CONNECTED")
    print("Type 'exit' to stop.\n")

    while True:
        command = input("You: ")
        response = jarvis.process_command(command)
        print(f"JARVIS: {response}")

        if command.lower().strip() in ["exit", "quit"]:
            break
