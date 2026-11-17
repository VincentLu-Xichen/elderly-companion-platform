"""First-lesson constants extracted without executing old course modules."""

PRACTICE_PLANS = {'lesson-1': '这周愿意时，留意一件小事，分开记下事情、想法、心情和做法；只在心里回想也可以。'}

LESSON_1_DEMONSTRATION = '先看一个示范：朋友没有回电话，小林想到‘他是不是不愿理我’，感到失落，于是没有再联系。没有回电话是发生的事，‘他是不是不愿理我’是想法，失落是心情，没有再联系是做法。这几部分可能相互影响。'

STORY_A = '别人和我说话或者打招呼时，我一时没有想到合适的回应。我想到：‘要是自己不回应，对方就会觉得我不礼貌、对聊天没有兴趣，这样会影响我们的关系。’我感到紧张，接着不断找话题，和对方说话。'

STORY_B = '老李到图书馆借书，门口贴着‘今日临时闭馆’。他想到：‘我今天的安排全乱了。’他有些失望，随后转身回家。'

QUESTIONS = ({'field': 'situation',
  'label': '事情',
  'prompt': '这段描述中，哪部分是在描述情境？',
  'expected': '别人说话或打招呼时，我一时没有想到合适的回应。',
  'hint': '找当时发生的具体情形，和对方可能怎样看我的解释分开。'},
 {'field': 'thought',
  'label': '想法',
  'prompt': '哪部分是在描述当时的想法？',
  'expected': '担心不回应会被认为不礼貌、没兴趣，并影响关系。',
  'hint': '想法是对事情的解释、判断或预测。'},
 {'field': 'emotion',
  'label': '心情',
  'prompt': '哪部分是在描述情绪？',
  'expected': '紧张。',
  'hint': '情绪是主观感受，请找故事中明确说出的感受。'},
 {'field': 'behavior',
  'label': '做法',
  'prompt': '哪部分是在描述实际行为？',
  'expected': '不断找话题，接着和对方说话。',
  'hint': '找实际做出的动作，区分愿望、预测和行动。'})

RETRY_QUESTIONS = ({'field': 'thought',
  'label': '想法',
  'prompt': '老李脑中出现了哪句话？',
  'expected': '我今天的安排全乱了。',
  'hint': '想法是对事情的解释、判断或预测。'},
 {'field': 'emotion',
  'label': '心情',
  'prompt': '故事明确说到，老李是什么心情？',
  'expected': '失望。',
  'hint': '情绪是主观感受，请找故事中明确说出的感受。'})

HARD_SAFETY_SIGNALS = ('想死', '不想活', '自杀', '结束生命', '伤害自己', '伤害别人')
