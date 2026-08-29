"""Convert a task_decomposition output (out/<scenario>/<i>.json) into the
`schedule` block used by the scheduling project's office_p.json.

Only the `schedule` field is produced. The `evaluation`, `solver` and
`chains` blocks are results of the CP-SAT solve and are deliberately not
fabricated here. The per-action `region` field is omitted for the same
reason: it depends on the physical layout of the scene, which the plan
does not carry.

Run from this directory:
    python to_schedule.py --input out/office_p/0.json --output schedule.json
"""
import argparse
import json
import re
import sys

# Locations the plan can refer to but that never appear in
# `object_names`. Used only to recognise resource names in the natural
# language step instructions.
KNOWN_LOCATIONS = (
    'desktop_surface',
    'pen_holder',
    'trash_bin',
    'laptop',
    'handover_zone',
)

# Durations observed in the reference schedule: 5s normally, 4s whenever a
# handover zone is involved.
DURATION = 5
DURATION_HANDOVER = 4
HANDOVER = 'handover_zone'

# The scheduling project's skill vocabulary. Anything else is refused
# rather than guessed at, so a stale plan built from the old primitive
# action list cannot be silently mangled into a schedule.
SKILLS = ('pick', 'place', 'flap_close', 'adjust')

# Natural-language phrase -> canonical resource name.
ALIASES = {
    'desktop': 'desktop_surface',
    'desk': 'desktop_surface',
    'desktop surface': 'desktop_surface',
    'pen holder': 'pen_holder',
    'trash bin': 'trash_bin',
    'bin': 'trash_bin',
    'laptop lid': 'laptop',
    'lid': 'laptop',
    'handover zone': HANDOVER,
    # the lid is not a separate resource in the scheduler's vocabulary
    'laptop_lid': 'laptop',
}

PICK_RE = re.compile(
    r'pick up (?:the )?(.+?) from (?:the )?(.+?)\s*$', re.I)
PLACE_RE = re.compile(
    r'place (?:the )?(.+?) (?:into|onto|on|in) (?:the )?(.+?)\s*$', re.I)


def canon(phrase):
    """Normalise a natural-language noun phrase to a resource name."""
    p = phrase.strip().strip('.').lower()
    p = re.sub(r'^(the|a|an) ', '', p)
    if p in ALIASES:
        return ALIASES[p]
    return p.replace(' ', '_')


def parse_step(skill, text, vocab):
    """Return (source, target) for one step, or raise ValueError."""
    if skill not in SKILLS:
        raise ValueError(
            'unknown skill %r; expected one of %s. The plan was probably '
            'generated with a different ROBOT ACTION LIST.'
            % (skill, ', '.join(SKILLS)))
    if skill == 'pick':
        m = PICK_RE.search(text)
        if not m:
            raise ValueError('cannot parse pick step: %r' % text)
        return canon(m.group(2)), canon(m.group(1))
    if skill == 'place':
        m = PLACE_RE.search(text)
        if not m:
            raise ValueError('cannot parse place step: %r' % text)
        return canon(m.group(1)), canon(m.group(2))
    # flap_close / adjust take a target only; find the first known object.
    for name in sorted(vocab, key=len, reverse=True):
        if re.search(r'\b%s\b' % name.replace('_', '[ _]'), text, re.I):
            return None, canon(name)
    raise ValueError('no known object in %s step: %r' % (skill, text))


def convert(doc):
    cohesion = doc['task_cohesion']
    sequence = cohesion['task_sequence']
    steps = cohesion['step_instructions']
    if len(sequence) != len(steps):
        raise ValueError('task_sequence and step_instructions differ in length')

    vocab = set(KNOWN_LOCATIONS)
    vocab.update(n.strip('<>') for n in cohesion.get('object_names', []))

    arms = {'left': [], 'right': []}
    clock = {'left': 0, 'right': 0}
    # last pick of an object per arm, so a place can point at it
    holding = {'left': {}, 'right': {}}

    for node_id, (raw, text) in enumerate(zip(sequence, steps), start=1):
        m = re.match(r'(\w+)\((left|right)\)\s*$', raw.strip())
        if not m:
            raise ValueError('unexpected action syntax: %r' % raw)
        skill, arm = m.group(1), m.group(2)
        source, target = parse_step(skill, text, vocab)

        params = {}
        if source is not None:
            params['source'] = source
        params['target'] = target
        params['arm'] = arm

        preconditions = []
        if skill == 'place' and source in holding[arm]:
            preconditions.append(holding[arm].pop(source))

        locked = [arm]
        if source is not None:
            locked.append(source)
        locked.append(target)

        dur = DURATION_HANDOVER if HANDOVER in (source, target) else DURATION
        start = clock[arm]
        clock[arm] = start + dur

        action_id = '%s%d' % (arm[0].upper(), len(arms[arm]) + 1)
        if skill == 'pick':
            holding[arm][target] = action_id

        arms[arm].append({
            'action_id': action_id,
            'node_id': node_id,
            'skill': skill,
            'parameters': params,
            'agents': [arm],
            'preconditions': preconditions,
            'locked_resources': locked,
            'scheduled_start_s': start,
            'scheduled_end_s': clock[arm],
            'arm_num': 1,
            'sync_with': [],
        })

    return {
        'total': max(clock['left'], clock['right']),
        'left': arms['left'],
        'right': arms['right'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()

    with open(args.input) as f:
        doc = json.load(f)
    try:
        schedule = convert(doc)
    except ValueError as exc:
        sys.exit('conversion failed: %s' % exc)

    text = json.dumps({'schedule': schedule}, indent=2)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(text + '\n')
        print('wrote ' + args.output)
    else:
        print(text)


if __name__ == '__main__':
    main()
