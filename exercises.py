"""
CBT Exercises
Collection of exercises for each distortion group
"""

import random

EXERCISES = {
    "G1": [
        {
            "id": "g1_spectrum",
            "name": "The Spectrum Exercise",
            "duration": "5 minutes",
            "description": "Practice seeing things on a scale instead of in black and white.",
            "instructions": [
                "Think of a recent situation you judged as 'all bad' or 'a complete failure'",
                "Draw a line from 0 to 10 (or imagine one)",
                "Place the situation on the spectrum - where does it really fall?",
                "Write down one thing that went okay and one thing to improve"
            ]
        },
        {
            "id": "g1_word_swap",
            "name": "Word Swap Challenge",
            "duration": "3 minutes",
            "description": "Replace extreme words with more balanced ones.",
            "instructions": [
                "Catch yourself using words like: always, never, completely, totally, worst, ruined",
                "Swap them for: sometimes, often, partially, mostly",
                "Example: 'I always mess up' → 'I sometimes make mistakes'",
                "Notice how the new sentence feels different"
            ]
        },
        {
            "id": "g1_both_true",
            "name": "Both Can Be True",
            "duration": "5 minutes",
            "description": "Practice holding two things as true at once.",
            "instructions": [
                "Think of something you're struggling with",
                "Complete this sentence: 'I'm struggling with ___ AND I'm also ___'",
                "Example: 'I'm struggling with this project AND I'm also making progress'",
                "Write down 3 'AND' statements about your current situation"
            ]
        }
    ],
    "G2": [
        {
            "id": "g2_evidence",
            "name": "Evidence Detective",
            "duration": "5 minutes",
            "description": "Examine the evidence for and against your belief.",
            "instructions": [
                "Write down a prediction or assumption you're making",
                "List evidence that SUPPORTS this belief",
                "List evidence that CONTRADICTS this belief",
                "Write a more balanced conclusion based on ALL the evidence"
            ]
        },
        {
            "id": "g2_alternative",
            "name": "Three Explanations",
            "duration": "3 minutes",
            "description": "Generate alternative explanations for a situation.",
            "instructions": [
                "Think of a situation where you assumed you knew why something happened",
                "Come up with 3 OTHER possible explanations",
                "Rate how likely each explanation is (including your original)",
                "Notice if your original assumption is really the most likely"
            ]
        },
        {
            "id": "g2_friend",
            "name": "Friend Perspective",
            "duration": "3 minutes",
            "description": "See the situation through a friend's eyes.",
            "instructions": [
                "Imagine a good friend is in your exact situation",
                "What would you tell them about their assumption?",
                "Would you believe their prediction is definitely true?",
                "Now apply that same compassionate logic to yourself"
            ]
        }
    ],
    "G3": [
        {
            "id": "g3_gratitude",
            "name": "Three Good Things",
            "duration": "5 minutes",
            "description": "Balance your focus by noticing positives.",
            "instructions": [
                "Write down 3 good things from today (even tiny ones)",
                "For each one, write WHY it happened",
                "Notice how it feels to focus on these",
                "Try this every evening for a week"
            ]
        },
        {
            "id": "g3_full_story",
            "name": "The Full Story",
            "duration": "5 minutes",
            "description": "Tell the complete story, not just the negative parts.",
            "instructions": [
                "Think of a situation you've been viewing negatively",
                "Write the FULL story including: what went wrong, what went okay, what you learned",
                "Read it back - does it feel different than your original view?",
                "Practice telling yourself the full story, not just the hard parts"
            ]
        },
        {
            "id": "g3_strengths",
            "name": "Strength Spotting",
            "duration": "3 minutes",
            "description": "Recognize your strengths in action.",
            "instructions": [
                "Think of a recent challenge you faced",
                "List 3 strengths you used to deal with it",
                "Even if it didn't go perfectly, what did you do right?",
                "Acknowledge yourself for those strengths"
            ]
        }
    ],
    "G4": [
        {
            "id": "g4_feelings_facts",
            "name": "Feelings vs Facts",
            "duration": "5 minutes",
            "description": "Separate what you feel from what is objectively true.",
            "instructions": [
                "Write down something you believe when you're upset",
                "Label it: Is this a FEELING or a FACT?",
                "If it's a feeling, rewrite it as: 'I feel ___ but that doesn't mean ___'",
                "Example: 'I feel like a failure' → 'I feel disappointed but that doesn't mean I am a failure'"
            ]
        },
        {
            "id": "g4_should_prefer",
            "name": "Should → Prefer",
            "duration": "3 minutes",
            "description": "Replace rigid shoulds with flexible preferences.",
            "instructions": [
                "Catch a 'should' statement you tell yourself",
                "Rewrite it as a preference: 'I would prefer...' or 'I'd like...'",
                "Example: 'I should never make mistakes' → 'I'd prefer to get things right, but mistakes help me learn'",
                "Notice how the preference feels less pressuring"
            ]
        },
        {
            "id": "g4_self_compassion",
            "name": "Compassionate Response",
            "duration": "5 minutes",
            "description": "Practice responding to yourself with kindness.",
            "instructions": [
                "Think of something you're being hard on yourself about",
                "What would you say to a friend in this situation?",
                "Write that compassionate response down",
                "Read it to yourself as if a caring friend is saying it to you"
            ]
        }
    ]
}


def get_exercise_for_group(group: str) -> dict:
    """
    Get a random exercise for the given distortion group.
    
    Args:
        group: Distortion group (G1, G2, G3, G4)
        
    Returns:
        Exercise dict with id, name, duration, description, instructions
    """
    if group not in EXERCISES:
        return None
    
    return random.choice(EXERCISES[group])


def get_all_exercises_for_group(group: str) -> list:
    """Get all exercises for a group."""
    return EXERCISES.get(group, [])


def get_exercise_by_id(exercise_id: str) -> dict:
    """Get a specific exercise by ID."""
    for group_exercises in EXERCISES.values():
        for exercise in group_exercises:
            if exercise["id"] == exercise_id:
                return exercise
    return None


# Test if run directly
if __name__ == "__main__":
    print("Testing exercises module:\n")
    
    for group in ["G1", "G2", "G3", "G4"]:
        exercise = get_exercise_for_group(group)
        print(f"{group}: {exercise['name']}")
        print(f"   Duration: {exercise['duration']}")
        print(f"   {exercise['description']}")
        print()
