import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from identity import IdentityResolver
from intent import classify
from models import EvidenceSource,EvidenceFact,ResourceState
from evidence import json_parser,sql_parser,log_parser,text_parser
from evidence.normalize import normalize
from resolver import resolve
from policy import Policy
from planner import plan,sort_key
from corpus import read_csv

NOW='2026-06-01T00:00:00Z'
SOURCE=EvidenceSource('fixture','fixture','account_service',NOW)


class CoreTests(unittest.TestCase):
    def parse(self,adapter,text):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture';p.write_text(text)
            return adapter.parse(p,SOURCE)[0]

    def test_intent(self):
        for text in ['Please delete my account.','Solicito la eliminación de mi cuenta.','このアカウントの削除を依頼します。','계정 삭제를 요청합니다.','Please remove my name and contact details, but keeping an internal deleted-account reference is fine.']:
            self.assertEqual(classify(text)[0],'DELETE',text)
        for text in ["Send a copy of my data. Do not delete my account.",'Please remove me from marketing lists only.','My surname is misspelled on the account.']:
            self.assertEqual(classify(text)[0],'NON_DELETE',text)

    def test_historical_identity_and_decoy(self):
        current=[dict(user_id='user_90001',email='NEW@example.test',phone='+1 212 555 0100',name='Example',email_hash='',updated_at=NOW)]
        events=[dict(user_id='user_90001',field_name='email',old_value='old@example.test',new_value='NEW@example.test',event_time='2026-05-01T00:00:00Z')]
        resolver=IdentityResolver(current,events)
        identity=resolver.resolve(' OLD@example.test ',NOW)
        self.assertEqual(identity.emails,{'old@example.test','new@example.test'})
        self.assertIn('12125550100',identity.phones)
        with self.assertRaises(ValueError):resolver.resolve('oldd@example.test',NOW)
        self.assertNotIn('new@example.test',resolver.resolve('old@example.test','2026-04-01T00:00:00Z').emails)

    def test_json_null_profile_is_absent(self):
        text=json.dumps(dict(exported_at=NOW,service_exports={'account_service':{'profile_lookups':[dict(resource_id='profile-z',profile=None,status_code=404,observed_at=NOW)]}}))
        self.assertEqual(self.parse(json_parser,text)[0].state,'ABSENT')

    def test_sql_replica_is_not_erased_by_primary(self):
        sql="CREATE TABLE customer_profiles_primary(resource_id TEXT,email TEXT); CREATE TABLE customer_profiles_replica(resource_id TEXT,email TEXT); INSERT INTO customer_profiles_replica VALUES ('profile-z','old@example.test');"
        facts=self.parse(sql_parser,sql)
        self.assertEqual(facts[0].state,'PRESENT')
        self.assertEqual(facts[0].system_id,'account_service')

    def test_log_trace_link(self):
        text=f'{NOW} level=DEBUG service=account_service trace_id=t1 event=profile_lookup_started lookup_key=old@example.test\n{NOW} level=INFO service=account_service trace_id=t1 event=profile_lookup_completed resource_id=profile-z rows=0 http_status=404'
        f=self.parse(log_parser,text)[0]
        self.assertEqual(f.state,'ABSENT');self.assertIn('old@example.test',f.identifiers)

    def test_activity_success_not_readback(self):
        self.assertEqual(self.parse(log_parser,f'{NOW} service=account_service event=DELETE_RECORD resource_id=profile-z result=SUCCESS'),[])

    def test_text(self):
        facts=self.parse(text_parser,f'- {NOW} | integration_service | flow-z | DATA_FLOW | ACTIVE | old@example.test')
        self.assertEqual(facts[0].state,'ACTIVE')

    def test_future_capture_excluded(self):
        f=normalize(dict(resource_id='profile-z',email='old@example.test'),SOURCE,'account_service','customer_profiles','2026-01-01T00:00:00Z')
        self.assertEqual(resolve([f],'2026-05-01T00:00:00Z'),[])

    def policy(self):
        return Policy(read_csv(Path(__file__).resolve().parents[2]/'dataset/deletion_rules.csv'))

    def test_tombstone_keeps_stable_reference(self):
        f=normalize(dict(resource_id='tomb-z',subject_reference='user_90001',name=None,email=None,phone=None,email_hash=None),SOURCE,'identity_service','deleted_customer_references')
        d=self.policy().evaluate(ResourceState(f),NOW)
        self.assertTrue(d.compliant);self.assertEqual(d.expected,'REDACTED')

    def test_tombstone_pii_is_redacted(self):
        f=normalize(dict(resource_id='tomb-z',subject_reference='user_90001',email='old@example.test'),SOURCE,'identity_service','deleted_customer_references')
        status,steps=plan([self.policy().evaluate(ResourceState(f),NOW)])
        self.assertEqual(status,'INCOMPLETE');self.assertEqual(steps[1]['operation'],'REDACT_RECORD')

    def test_active_flow_and_retained_security(self):
        flow=normalize(dict(resource_id='flow-z',enabled=True,customer_reference='user_90001'),SOURCE,'integration_service','connectors')
        security=normalize(dict(resource_id='audit-z',subject_reference='user_90001',retention_until='2030-01-01T00:00:00Z'),SOURCE,'security_service','audit_records')
        status,steps=plan([self.policy().evaluate(ResourceState(f),NOW) for f in [flow,security]])
        self.assertEqual(status,'INCOMPLETE')
        self.assertIn('VERIFY_RECORD_PRESENT',[s['operation'] for s in steps])
        self.assertEqual(steps[1]['operation'],'DISABLE_DATA_FLOW')
        self.assertTrue(all(s['evidence_id']=='' for s in steps if s['phase']!='FINDING'))
        self.assertEqual(steps,sorted(steps,key=sort_key))
        self.assertEqual([s['step_no'] for s in steps],list(range(1,len(steps)+1)))

    def test_backup_is_blocked_not_deleted(self):
        f=normalize(dict(resource_id='backup-z',restore_allowed=True,subject_reference='user_90001'),SOURCE,'backup_service','restore_entries')
        status,steps=plan([self.policy().evaluate(ResourceState(f),NOW)])
        self.assertEqual(status,'INCOMPLETE')
        self.assertEqual(steps[1]['operation'],'BLOCK_RESTORE')

    def test_analytics_stable_reference_is_not_anonymous(self):
        f=normalize(dict(resource_id='analytics-z',user_id='user_90001',email=None),SOURCE,'analytics_platform','customer_analytics_reports')
        self.assertEqual(f.state,'PII')


if __name__=='__main__':unittest.main()
