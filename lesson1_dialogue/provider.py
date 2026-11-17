"""One call through existing provider clients; no implicit fallback or repairs."""
import copy
import hashlib
import json
import time


class ProviderClient:
    def __init__(self, client=None):
        self._client=client
        self.model_calls=[]
        self.completion=None

    def complete(self, request):
        return self._complete(request)

    def complete_stream(self, request, on_reply_delta):
        return self._complete(request, on_reply_delta=on_reply_delta)

    def _complete(self, request, *, on_reply_delta=None):
        if self._client is None:
            from lesson1_support.client import client_from_env
            self._client=client_from_env()
        call={"phase":request.purpose,"status":"pending",
              "prompt_hash":hashlib.sha256(request.system_prompt.encode()).hexdigest()}
        self.model_calls.append(call)
        started=time.perf_counter()
        messages=[{"role":"system","content":request.system_prompt},
                  {"role":"user","content":json.dumps({"context":request.context,
                     "output_schema":request.output_schema},ensure_ascii=False)}]
        call["input_messages"]=copy.deepcopy(messages)
        try:
            parameters={"temperature":1.0,"max_completion_tokens":1200,
                        "response_format":{"type":"json_object"}}
            if on_reply_delta is None:
                result=self._client.complete_with_metadata(messages,**parameters)
            else:
                from .reply_stream import ReplyProjector
                projector=ReplyProjector();result=None
                call.update(transport='stream',reply_delta_count=0)
                for chunk in self._client.stream_with_metadata(messages,**parameters):
                    if chunk.delta:
                        addition=projector.feed(chunk.delta)
                        if addition:
                            call.setdefault('first_reply_delta_ms',int((time.perf_counter()-started)*1000))
                            call['reply_delta_count']+=1
                            on_reply_delta(addition)
                    if chunk.completion is not None:
                        if result is not None:raise RuntimeError('duplicate_stream_completion')
                        result=chunk.completion
                if result is None or result.text!=projector.raw:
                    raise RuntimeError('incomplete_or_changed_stream')
            self.completion=result
            call.update(model=result.model,usage=result.usage,request_id=result.request_id,
                        finish_reason=result.finish_reason,raw_output=result.text)
            if result.finish_reason not in {"","stop"}:raise RuntimeError("incomplete_completion")
            if on_reply_delta is not None:
                addition=projector.finish()
                if addition:
                    call.setdefault('first_reply_delta_ms',int((time.perf_counter()-started)*1000))
                    call['reply_delta_count']+=1
                    on_reply_delta(addition)
            call["status"]="success"
            return result.text
        except Exception as exc:
            call.update(status="error",error_type=type(exc).__name__)
            raise
        finally:call["latency_ms"]=int((time.perf_counter()-started)*1000)


def runtime_factory():
    from .runtime import DialogueRuntime
    from lesson1_support.content import HARD_SAFETY_SIGNALS
    client=ProviderClient()
    return DialogueRuntime(client,safety_guard=lambda m:any(word in m.text for word in HARD_SAFETY_SIGNALS))
