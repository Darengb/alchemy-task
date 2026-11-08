"""Temporary synthetic registered-handler transport canary, no source/task access."""
import json
import os
import threading
import time


def running_remaining(start_epoch, observed_epoch, monotonic_now, budget=1800.0):
    """Conservative epoch-to-monotonic conversion with no budget extension."""
    return monotonic_now + max(0.0, budget - max(0.0, observed_epoch - start_epoch))


def register(ctx):
    def sleep_probe(args, **kwargs):
        seconds = float(args.get('seconds', 1850))
        if not 0 <= seconds <= 1900:
            raise ValueError('seconds must be between 0 and 1900')
        label = str(args.get('label', 'synthetic'))
        if not label.replace('-', '').replace('_', '').isalnum() or len(label) > 80:
            raise ValueError('invalid synthetic label')
        start_epoch, start_mono = time.time(), time.monotonic()
        receipt = {'label': label, 'requested_seconds': seconds,
                   'started_epoch': start_epoch, 'pid': os.getpid(),
                   'thread': threading.current_thread().name,
                   'state': 'started'}
        ctx.state.set('budget:' + label, receipt)
        time.sleep(seconds)
        receipt.update(state='completed', completed_epoch=time.time(),
                       duration_seconds=time.monotonic() - start_mono)
        ctx.state.set('budget:' + label, receipt)
        return json.dumps(receipt)

    def receipt(args, **kwargs):
        return json.dumps(ctx.state.get('budget:' + args['label'], default={}))

    for name, handler, properties, required, description in [
        ('discovery_budget_sleep', sleep_probe,
         {'seconds': {'type': 'number', 'minimum': 0, 'maximum': 1900},
          'label': {'type': 'string'}}, ['seconds', 'label'],
         'Synthetic registered host transport canary. Waits requested real seconds and returns duration receipt.'),
        ('discovery_budget_receipt', receipt, {'label': {'type': 'string'}}, ['label'],
         'Read synthetic canary start or completion receipt without waiting.')]:
        ctx.register_tool(name=name, toolset='alchemy-discovery-budget-probe', handler=handler,
                          schema={'name': name, 'description': description,
                                  'parameters': {'type': 'object', 'properties': properties,
                                                 'required': required, 'additionalProperties': False}},
                          description=description)
