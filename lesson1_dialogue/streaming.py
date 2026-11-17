"""One owned service transaction behind bounded, provisional reply-only SSE events."""
import logging
import time
from queue import Empty,Full,Queue
from threading import Event,Thread

from .public_errors import NOTICES,public_notice


def stream_turn(*,session_factory,participant_id,conversation_id,content,idempotency_key,
                expected_revision,action='chat',runtime_factory=None,disconnect_event=None):
    queue=Queue(maxsize=32);disconnected=disconnect_event or Event()
    def publish(item):
        while not disconnected.is_set():
            try:queue.put(item,timeout=.1);return
            except Full:continue
    def work():
        from . import services
        try:
            with session_factory() as db:
                result=services.process(db,participant_id=participant_id,conversation_id=conversation_id,
                    content=content,idempotency_key=idempotency_key,expected_revision=expected_revision,
                    action=action,runtime_factory=runtime_factory,
                    on_reply_delta=lambda text:publish({'type':'reply_delta','text':text}))
            publish({'type':'result','data':result})
        except Exception as exc:
            notice=public_notice(exc,is_turn=True)
            logging.getLogger(__name__).warning('dialogue_stream_failed notice=%s conversation_id=%s',notice,conversation_id)
            _,_,recovery,outcome=NOTICES[notice]
            publish({'type':'error','notice':notice,'recovery':recovery,'outcome':outcome})
    Thread(target=work,daemon=True,name='lesson1-dialogue-stream').start()
    try:
        yield {'type':'start'}
        last_heartbeat=time.monotonic()
        while not disconnected.is_set():
            try:item=queue.get(timeout=.25)
            except Empty:
                if time.monotonic()-last_heartbeat>=10:
                    last_heartbeat=time.monotonic();yield {'type':'heartbeat'}
                continue
            yield item
            if item['type'] in {'result','error'}:break
    finally:
        # A disconnected browser stops publication, not an already-started save.
        disconnected.set()
