"""
Groq API Client
Generates therapeutic responses using LLaMA 3
"""

import json
from groq import Groq


class GroqClient:
    """
    Client for Groq API to generate therapeutic responses.
    Uses LLaMA 3.3 70B for warm, empathetic responses.
    """
    
    MODEL = "llama-3.3-70b-versatile"
    
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GROQ_API_KEY is required")
        self.client = Groq(api_key=api_key)
        print(f"✅ Groq client initialized with model: {self.MODEL}")
    
    def generate_therapeutic_response(
        self,
        user_message: str,
        conversation_history: list,
        user_name: str,
        user_context: str,
        detected_group: str,
        current_stage: int,
        stage_goal: str,
        stage_instruction: str
    ) -> dict:
        """
        Generate a therapeutic response based on the current stage.
        
        Returns:
            dict with 'response' and 'advance_to_next_stage' flag
        """
        
        # Build conversation context
        history_text = self._format_history(conversation_history)
        
        system_prompt = f"""You are a warm, caring CBT companion talking to {user_name}, a {user_context}. 
You speak like a supportive friend - not a clinical therapist. Use casual, warm language.

CURRENT SITUATION:
- Detected thinking pattern: {detected_group}
- Current stage: {current_stage} of 3
- Stage goal: {stage_goal}

YOUR TASK FOR THIS STAGE:
{stage_instruction}

IMPORTANT RULES:
1. Use {user_name}'s name naturally (not every message, but occasionally)
2. Keep responses medium length (2-4 sentences usually)
3. Be warm and validating first, then gently guide
4. Don't use clinical jargon - speak like a friend
5. Don't lecture or be preachy
6. Ask ONE question at a time, if any

STAGE ADVANCEMENT GUIDELINES:
{"STAGE 3 IS SPECIAL: This is the final stage. Do NOT try to end or wrap up. Just keep being supportive and helpful until " + user_name + " naturally wants to stop. Set advance_to_next_stage to FALSE always." if current_stage == 3 else '''Set "advance_to_next_stage" to TRUE when ''' + user_name + ''' shows reasonable progress:
- They're engaging with the idea (not just "yeah" but some reflection)
- They've acknowledged or explored the concept
- They seem ready to move forward
- You've made your key therapeutic point for this stage

Set "advance_to_next_stage" to FALSE when:
- ''' + user_name + ''' is still venting or needs to be heard
- They seem confused or resistant
- You haven't yet introduced the core idea of this stage
- They gave a very short/dismissive response

Don't demand perfection. Progress over perfection.'''}

Respond in JSON format:
{{"response": "your message here", "advance_to_next_stage": {"false" if current_stage == 3 else "true/false"}}}"""

        user_prompt = f"""CONVERSATION SO FAR:
{history_text}

{user_name}'s latest message: "{user_message}"

Respond as the CBT companion. Remember: warm, friendly, like a supportive friend."""

        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            return {
                "response": result.get("response", "I hear you. Tell me more."),
                "advance_to_next_stage": result.get("advance_to_next_stage", False)
            }
            
        except json.JSONDecodeError:
            # If JSON parsing fails, extract response text
            return {
                "response": response.choices[0].message.content,
                "advance_to_next_stage": False
            }
        except Exception as e:
            print(f"Groq API error: {str(e)}")
            return {
                "response": f"I hear you, {user_name}. That sounds tough. Can you tell me more about what you're feeling?",
                "advance_to_next_stage": False
            }
    
    def generate_supportive_response(
        self,
        user_message: str,
        conversation_history: list,
        user_name: str
    ) -> str:
        """
        Generate a supportive response for G0 (no distortion) cases.
        Just listen and be supportive, gently ask if anything else is bothering them.
        """
        
        history_text = self._format_history(conversation_history)
        
        system_prompt = f"""You are a warm, caring companion talking to {user_name}. 
They're sharing something with you, and right now they don't seem to be caught in any negative thinking patterns.

YOUR TASK:
1. Listen and validate what they're sharing
2. Be warm and supportive
3. Gently ask if there's anything else on their mind or anything troubling them
4. Keep it conversational and friendly

IMPORTANT:
- Use {user_name}'s name occasionally (not every message)
- Keep responses short and warm (2-3 sentences)
- Don't be preachy or give unsolicited advice
- Just be a good listener and friend"""

        user_prompt = f"""CONVERSATION SO FAR:
{history_text}

{user_name}'s latest message: "{user_message}"

Respond warmly as their supportive companion."""

        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Groq API error: {str(e)}")
            return f"I hear you, {user_name}. Thanks for sharing that with me. Is there anything else on your mind?"
    
    def _format_history(self, history: list) -> str:
        """Format conversation history for the prompt."""
        if not history:
            return "(This is the start of the conversation)"
        
        formatted = []
        for msg in history:
            role = "User" if msg["role"] == "user" else "Companion"
            formatted.append(f"{role}: {msg['content']}")
        
        return "\n".join(formatted)


# Test if run directly
if __name__ == "__main__":
    import os
    
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        client = GroqClient(api_key)
        
        result = client.generate_therapeutic_response(
            user_message="I failed my exam and I feel like I'll never succeed at anything",
            conversation_history=[],
            user_name="Max",
            user_context="college student",
            detected_group="G2",
            current_stage=1,
            stage_goal="Make underlying assumption explicit",
            stage_instruction="Help Max identify the prediction or assumption he's making. Gently point out the overgeneralization."
        )
        
        print("Response:", result["response"])
        print("Advance:", result["advance_to_next_stage"])
    else:
        print("Set GROQ_API_KEY to test")
