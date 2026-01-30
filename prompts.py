"""
Prompts and Content
Stage goals, summaries, and other static content
"""

# Stage goals for each distortion group
STAGE_GOALS = {
    "G1": {
        1: {
            "name": "Recognize the Pattern",
            "goal": "Help them see the all-or-nothing thinking",
            "instruction": "Gently point out that they're using extreme/absolute language (always, never, completely, totally). Help them notice the black-and-white framing without being preachy."
        },
        2: {
            "name": "Find the Gray",
            "goal": "Explore the middle ground",
            "instruction": "Help them see that reality usually exists on a spectrum. Ask about exceptions or times when things weren't all bad/all good. Guide them to find nuance."
        },
        3: {
            "name": "Balanced View",
            "goal": "Develop a more balanced perspective",
            "instruction": "Help them form a more balanced statement that acknowledges both struggles AND strengths/exceptions. Celebrate any shift toward nuanced thinking."
        }
    },
    "G2": {
        1: {
            "name": "Spot the Assumption",
            "goal": "Identify the overgeneralization or prediction",
            "instruction": "Help them notice they're making a broad conclusion from limited evidence, or predicting the future/reading minds. Gently highlight the assumption."
        },
        2: {
            "name": "Examine the Evidence",
            "goal": "Look at actual evidence",
            "instruction": "Ask what evidence supports or contradicts their belief. Help them see they might be jumping to conclusions. Explore alternative explanations."
        },
        3: {
            "name": "Reality Check",
            "goal": "Form a more realistic view",
            "instruction": "Help them develop a more evidence-based perspective. Acknowledge uncertainty is okay. Celebrate willingness to consider other possibilities."
        }
    },
    "G3": {
        1: {
            "name": "Notice the Focus",
            "goal": "Recognize the negative filter",
            "instruction": "Help them see they might be focusing heavily on negatives while filtering out positives. Gently point out what they might be overlooking."
        },
        2: {
            "name": "Widen the Lens",
            "goal": "Bring in the full picture",
            "instruction": "Ask about positives they might be discounting. Help them recall good things or strengths. Balance the perspective without dismissing their struggles."
        },
        3: {
            "name": "Full Picture",
            "goal": "See both positives and negatives",
            "instruction": "Help them hold both the difficulties AND the good things. Develop a more complete view. Celebrate their ability to see the bigger picture."
        }
    },
    "G4": {
        1: {
            "name": "Feelings vs Facts",
            "goal": "Separate emotions from reality",
            "instruction": "Help them see they might be treating feelings as facts, or taking things too personally, or using 'should' rigidly. Validate feelings while questioning conclusions."
        },
        2: {
            "name": "Challenge the Logic",
            "goal": "Examine the reasoning",
            "instruction": "Explore whether their conclusion logically follows. Just because they feel something doesn't make it true. Help them see other interpretations."
        },
        3: {
            "name": "New Perspective",
            "goal": "Develop healthier self-talk",
            "instruction": "Help them reframe with more compassion and flexibility. Replace rigid 'shoulds' with preferences. Celebrate growth in self-compassion."
        }
    }
}

# Session summaries (shown at end)
SUMMARIES = {
    "G1": """✨ **Great work today!**

You practiced noticing all-or-nothing thinking and finding the middle ground. Remember: life rarely fits into neat boxes of "always" or "never." The truth usually lives somewhere in between.

Keep noticing when you use extreme words, and gently remind yourself to look for the gray areas. 💙""",

    "G2": """✨ **Great work today!**

You practiced catching those assumptions and predictions your mind makes, and checking them against actual evidence. Our brains love to jump to conclusions, but we don't have to believe every thought!

Keep asking yourself: "What's the evidence? Is there another way to see this?" 💙""",

    "G3": """✨ **Great work today!**

You practiced widening your focus to see the full picture, not just the negatives. It's natural to notice what's wrong, but there's usually more to the story.

Keep practicing noticing the good stuff too, even the small things. They count! 💙""",

    "G4": """✨ **Great work today!**

You practiced separating feelings from facts and being more flexible with yourself. Emotions are real, but they're not always accurate reporters of reality.

Keep practicing self-compassion and replacing rigid "shoulds" with gentler preferences. You deserve kindness - especially from yourself! 💙"""
}

# Natural conversation endings
NATURAL_ENDINGS = [
    "Take care of yourself, {name}! I'm always here when you need to talk. 💙",
    "Glad I could help, {name}! Remember, you're doing better than you think. See you next time! 💙",
    "Bye for now, {name}! Be kind to yourself today. 💙",
    "Take it easy, {name}! You've got this. See you soon! 💙",
    "Catch you later, {name}! Remember, one step at a time. 💙"
]

# Greeting messages
GREETINGS = [
    "Hey {name}! 👋 What's on your mind today?",
    "Hi {name}! How are you doing? I'm here to listen.",
    "Hey there, {name}! 💙 What would you like to talk about?",
    "Hi {name}! Good to see you. What's going on?"
]
