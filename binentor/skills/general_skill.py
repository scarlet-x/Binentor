class GeneralSkill:

    async def execute(self, message, memory):

        return {
            "response": f"You said: {message}",
            "memory_update": None
        }
