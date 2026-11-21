import os, tempfile, subprocess, sys, json
from pathlib import Path

def test_cli_help():
    p=subprocess.run([sys.executable,'main.py','--help'],capture_output=True,text=True)
    assert p.returncode==0 and 'ingest' in p.stdout

def test_normalization():
    from workmate.engine import norm, client_for_question
    assert norm('Northbeam Retail!')=='northbeam retail'
    assert client_for_question('Who owns the CL fleet dashboard?')=='cobaltline'
    assert client_for_question('When is NB homepage due?')=='northbeam'

def test_forget_matches_topic_not_boilerplate():
    from workmate.engine import is_forgotten
    record={'body':'Planning Dubai trip 20–24 Nov with family.'}
    assert is_forgotten(record,['Please forget what I said about my Dubai trip'])
    assert not is_forgotten(record,['Forget my billing preference'])

def test_temporary_fact_expiry():
    from workmate.engine import record_is_expired
    leave={'at':'2026-11-04T04:00:00Z','body':"I'm on leave from 9 Nov till the 12th. back on 13 Nov."}
    assert not record_is_expired(leave,'2026-11-10T12:00:00Z')
    assert record_is_expired(leave,'2026-11-14T12:00:00Z')
    trip={'at':'2026-11-03T16:10:00Z','body':'Planning Dubai trip 20–24 Nov with family.'}
    assert not record_is_expired(trip,'2026-11-22T12:00:00Z')
    assert record_is_expired(trip,'2026-11-25T12:00:00Z')

def test_optional_model_adapter_does_not_require_provider_sdk(monkeypatch):
    from workmate.llm import complete_json
    monkeypatch.setenv('MODEL_PROVIDER', 'none')
    data, usage = complete_json('system', 'user')
    assert data is None
    assert usage['input_tokens'] == usage['output_tokens'] == 0

def test_model_json_parser_accepts_object_only():
    from workmate.llm import parse_json_response
    assert parse_json_response('```json\n{"ok": true}\n```') == {'ok': True}
    assert parse_json_response('[1, 2]') is None
    assert parse_json_response('not json') is None

def test_ingestion_supports_later_days_and_is_idempotent(tmp_path, monkeypatch):
    import json
    import workmate.engine as engine
    import workmate.storage as storage

    data = tmp_path / 'data'
    (data / 'days').mkdir(parents=True)
    (data / 'feedback').mkdir()
    (data / 'days' / 'day-06.jsonl').write_text(
        json.dumps({
            'id': 'later-record', 'org': 'org_kp', 'type': 'note',
            'at': '2026-11-07T10:00:00Z', 'author': 'p02',
            'client': None, 'visibility': 'team', 'body': 'Day six'
        }) + '\n', encoding='utf-8'
    )
    (data / 'feedback' / 'day-05.jsonl').write_text(
        json.dumps({
            'day': 5, 'person': 'p02', 'type': 'preference',
            'words': 'Max 5 changes per brief.'
        }) + '\n', encoding='utf-8'
    )
    monkeypatch.setattr(engine, 'DATA', data)
    monkeypatch.setattr(storage, 'DB_PATH', tmp_path / 'test.sqlite3')

    assert engine.ingest(6)['records_ingested'] == 1
    assert engine.ingest(6)['records_ingested'] == 1
    db = storage.connect()
    try:
        assert db.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] == 1
    finally:
        db.close()

def test_hinglish_promises_resolve_relative_deadlines():
    from workmate.engine import extract_promise, clean_text
    tomorrow = extract_promise({
        'id': 'r1', 'author': 'p02', 'at': '2026-11-02T09:35:00Z',
        'body': 'the checkout copy kal tak bhej dunga'
    })
    next_monday = extract_promise({
        'id': 'r2', 'author': 'p18', 'at': '2026-11-02T10:00:00Z',
        'body': 'the revised banner set next Monday tak share kar dungi/dunga, pakka.'
    })
    eod = extract_promise({
        'id': 'r3', 'author': 'p21', 'at': '2026-11-02T06:30:00Z',
        'body': 'Will share the API spec for the TMS feed by EOD today.'
    })
    conditional = extract_promise({
        'id': 'r4', 'author': 'p14', 'at': '2026-11-05T10:00:00Z',
        'body': "Kavya owns billing for NB right? I'll send the invoice query to her."
    })
    assert (tomorrow['owner'], tomorrow['due'], tomorrow['sources']) == ('p02', '2026-11-03', ['r1'])
    assert next_monday['due'] == '2026-11-09'
    assert eod['due'] == '2026-11-02'
    assert 'Kavya' not in conditional['what']
    assert clean_text('20\u00e2\u20ac\u201c24 Nov') == '20-24 Nov'
    assert clean_text('20\ufffd24 Nov') == '20-24 Nov'
    assert clean_text('20\u201324 Nov') == '20-24 Nov'
