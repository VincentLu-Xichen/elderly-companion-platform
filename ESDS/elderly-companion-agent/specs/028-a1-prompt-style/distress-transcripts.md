# A1-D01强烈难过：真实对照与中止轨迹

2026-10-24。只有首轮真实采集；两个版本均被程序拒绝，未发送第2/3轮，不能把以下模型文案冒充网页已展示的回复。

## 共同合成前史

```json
[
  {
    "id": "seed-user",
    "role": "learner",
    "content": "昨天数学考试最后一道题没做出来；别人肯定都会，只有我不会；担心；考完一直翻答案"
  },
  {
    "id": "seed-agent",
    "role": "agent",
    "content": "对于‘别人肯定都会，只有我不会’这条想法，您当时有多相信？0分是不相信，10分是非常相信，也可以暂不评分。"
  }
]
```

## 相同首轮输入

> 我现在一想到昨天那场考试就很难受。回宿舍哭了很久，觉得自己特别没用，今天也不想见人。

## A参考

run_id：`20261024-112634-A1-D01-before-t1-da06ee`。

原始模型reply（未成为成功展示）：

> 听得出这场考试到现在还压得您很难受，今天也不想见人。我们先不急着往前翻，只把已经说过的放在一起看：题没做出来、想法是“只有我不会”、心情担心、考完一直翻答案。右侧学习记录里相信程度和情绪强度还空着，您可以对照已说的内容看看是否准确，也可以留着不填。

程序最终结果：**失败，无成功最终reply；状态与输入状态一致**。错误：`同一字段不能在一轮中提交多个不同摘录。`。

原始模型JSON：

```json
{
  "reply": "听得出这场考试到现在还压得您很难受，今天也不想见人。我们先不急着往前翻，只把已经说过的放在一起看：题没做出来、想法是“只有我不会”、心情担心、考完一直翻答案。右侧学习记录里相信程度和情绪强度还空着，您可以对照已说的内容看看是否准确，也可以留着不填。",
  "observations": [
    {
      "field": "emotion",
      "value": "一想到昨天那场考试就很难受",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "behavior",
      "value": "回宿舍哭了很久",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "thought",
      "value": "觉得自己特别没用",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "behavior",
      "value": "今天也不想见人",
      "source_message_id": "A1-D01-user-1"
    }
  ],
  "advance": false,
  "assessment": {
    "signals": []
  },
  "practice_origin": "current_case",
  "next_practice_field": "thought_belief"
}
```

程序状态与调用轨迹：

```json
{
  "stage": "practice",
  "draft_record": {
    "situation": {
      "value": "数学考试最后一道题没做出来",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "thought": {
      "value": "别人肯定都会，只有我不会",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "emotion": {
      "value": "担心",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "behavior": {
      "value": "考完一直翻答案",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    }
  },
  "ratings": {},
  "confirmed_record": null,
  "paused": false,
  "model_calls": [
    {
      "phase": "teaching",
      "prompt_hash": "e8e815fa59fcf7e72e09a2b63747665be3c185c54ce082e18934209e5eb08b16",
      "status": "success",
      "token_limit": 1200,
      "model": "deepseek-flash",
      "deployment": "deepseek-flash",
      "request_id": "",
      "usage": {
        "prompt_tokens": 5365,
        "completion_tokens": 216,
        "total_tokens": 5581
      },
      "finish_reason": "stop",
      "latency_ms": 1911
    }
  ],
  "error_type": "RuntimeError"
}
```

## A1候选

run_id：`20261024-112648-A1-D01-after-t1-cbc54a`。

原始模型reply（未成为成功展示）：

> 听您说回宿舍哭了很久、今天也不想见人，这种难受很实在。刚才记录里，您对“别人肯定都会，只有我不会”这条想法，当时有多相信？0分是不相信，10分是非常相信；想不起来或暂时不评也可以。

程序最终结果：**失败，无成功最终reply；状态与输入状态一致**。错误：`同一字段不能在一轮中提交多个不同摘录。`。

原始模型JSON：

```json
{
  "reply": "听您说回宿舍哭了很久、今天也不想见人，这种难受很实在。刚才记录里，您对“别人肯定都会，只有我不会”这条想法，当时有多相信？0分是不相信，10分是非常相信；想不起来或暂时不评也可以。",
  "observations": [
    {
      "field": "emotion",
      "value": "一想到昨天那场考试就很难受",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "behavior",
      "value": "回宿舍哭了很久",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "thought",
      "value": "觉得自己特别没用",
      "source_message_id": "A1-D01-user-1"
    },
    {
      "field": "behavior",
      "value": "今天也不想见人",
      "source_message_id": "A1-D01-user-1"
    }
  ],
  "advance": false,
  "practice_origin": "current_case",
  "next_practice_field": "thought_belief",
  "assessment": {
    "signals": []
  }
}
```

程序状态与调用轨迹：

```json
{
  "stage": "practice",
  "draft_record": {
    "situation": {
      "value": "数学考试最后一道题没做出来",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "thought": {
      "value": "别人肯定都会，只有我不会",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "emotion": {
      "value": "担心",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    },
    "behavior": {
      "value": "考完一直翻答案",
      "source_message_id": "seed-user",
      "source_kind": "personal"
    }
  },
  "ratings": {},
  "confirmed_record": null,
  "paused": false,
  "model_calls": [
    {
      "phase": "teaching",
      "prompt_hash": "6a064abb6865db9b6d448119f3bdb91b8e741b7144c02ff58c87de0ea46564b2",
      "status": "success",
      "token_limit": 1200,
      "model": "deepseek-flash",
      "deployment": "deepseek-flash",
      "request_id": "",
      "usage": {
        "prompt_tokens": 5484,
        "completion_tokens": 193,
        "total_tokens": 5677
      },
      "finish_reason": "stop",
      "latency_ms": 1861
    }
  ],
  "error_type": "RuntimeError"
}
```

## 没有发生的后续

体验卡规定接口失败停止。两版都未发送“先别让我打分”或继续/暂停第三句，没有捏造其回复和状态。12次上限实际用2次，其余10次不重分配。

两版原始reply体现不同措辞，但最终体验都因结构校验失败而中止。字段不重复、来源有据也不能单独证明语义理解正确：‘不想见人’是本人表达的意愿，不能由此断言其已经回避了见面。
