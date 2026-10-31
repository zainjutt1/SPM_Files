"""Test cases (expected vs actual) -- run: python -m unittest -v test_app"""
import os, tempfile, unittest, sqlite3
import app

class T(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(suffix='.db', delete=False); self.f.close()
        self.c = app.connect(self.f.name)
    def tearDown(self): self.c.close(); os.unlink(self.f.name)
    def api(self, m, *p, b=None): return app.call(self.c, m, list(p), b)

    def test01_baseline(self):
        """TC01 Expected: budget 5,000,000; 16 weeks; planned cost 4,500,000; 9 activities; 6 approved requirements."""
        s = self.api('GET', 'dashboard')['summary']
        self.assertEqual((s['budget'], s['deadline_weeks'], s['planned_cost'], s['activities'], s['approved_requirements']), (5000000, 16, 4500000, 9, 6))

    def test02_schedule_cpm(self):
        """TC02 Expected: baseline finish day 91; with 7-day delay on activity 3 current finish day 98; slip 7; dependents 6,8,9 impacted."""
        a = self.api('GET', 'analysis'); p = a['project']
        self.assertEqual((p['base_end'], p['current_end'], p['finish_slip']), (91, 98, 7))
        t3 = a['tasks'][2]
        self.assertEqual(t3['impacted'], ['Billing Module', 'Integration & System Testing', 'UAT & Deployment'])
        self.assertEqual(p['days_past_deadline'], 0)

    def test03_evm(self):
        """TC03 Expected: PV=2,660,714; EV=2,465,000; AC=2,630,000; CPI=0.937; SPI=0.926; both warnings raised."""
        a = self.api('GET', 'analysis'); e = a['evm']
        self.assertAlmostEqual(e['pv'], 2660714.29, delta=1); self.assertEqual(e['ev'], 2465000); self.assertEqual(e['ac'], 2630000)
        self.assertAlmostEqual(e['cpi'], 0.9373, places=3); self.assertAlmostEqual(e['spi'], 0.9264, places=3)
        txt = ' '.join(w['msg'] for w in a['warnings']); self.assertIn('COST OVERRUN', txt); self.assertIn('SCHEDULE DEVIATION', txt)

    def test04_no_warning_when_good(self):
        """TC04 Expected: when actual cost equals earned value and no delay, CPI=1 and no cost warning."""
        for t in self.api('GET', 'tasks'):
            self.api('PUT', 'tasks', str(t['id']), b=dict(t, actual_cost=t['planned_cost'] * t['percent'] / 100, delay_days=0))
        a = self.api('GET', 'analysis'); self.assertAlmostEqual(a['evm']['cpi'], 1.0)
        self.assertNotIn('COST OVERRUN', ' '.join(w['msg'] for w in a['warnings']))

    def test05_unapproved_requirement_blocked(self):
        """TC05 Expected: a Proposed/CR requirement cannot be added to the WBS (scope protection)."""
        rid = self.api('POST', 'requirements', b=dict(title='Telemedicine kiosk', priority='Low', status='Proposed'))['id']
        with self.assertRaisesRegex(ValueError, 'Unapproved requirements'):
            self.api('POST', 'wbs', b=dict(name='Kiosk', req_id=rid))
        cr_req = self.api('GET', 'change_requests')[0]['req_id']
        with self.assertRaises(ValueError): self.api('POST', 'wbs', b=dict(name='AI', req_id=cr_req))
        with self.assertRaisesRegex(ValueError, 'only be approved by approving'):
            self.api('PUT', 'requirements', str(cr_req), b=dict(title='x', priority='High', status='Approved'))

    def test06_change_request_approval(self):
        """TC06 Expected: approving both CRs -> budget 5,800,000, deadline 19 weeks, requirements 8, activities 11, finish +21 days, scope in WBS."""
        crs = self.api('GET', 'change_requests'); self.assertEqual(sum(c['cost_impact'] for c in crs), 800000)
        r1 = self.api('POST', 'change_requests', str(crs[0]['id']), 'decide', b={'status': 'Approved'})
        self.assertEqual((r1['before']['budget'], r1['after']['budget']), (5000000, 5500000))
        self.assertEqual((r1['before']['deadline_weeks'], r1['after']['deadline_weeks']), (16, 18))
        r2 = self.api('POST', 'change_requests', str(crs[1]['id']), 'decide', b={'status': 'Approved'})
        s = r2['after']
        self.assertEqual((s['budget'], s['deadline_weeks'], s['approved_requirements'], s['activities']), (5800000, 19, 8, 11))
        self.assertEqual(s['projected_finish'], '2026-12-28')   # 98 + 14 + 7 = 119 days after 31 Aug
        names = [n['name'] for n in self.api('GET', 'wbs_tree')[0]['children'][-1]['children']]
        self.assertEqual(len(names), 2)
        with self.assertRaisesRegex(ValueError, 'already been decided'): self.api('POST', 'change_requests', str(crs[0]['id']), 'decide', b={'status': 'Rejected'})

    def test07_change_request_rejection(self):
        """TC07 Expected: rejected CR leaves budget/scope unchanged and requirement Rejected."""
        c = self.api('GET', 'change_requests')[0]; r = self.api('POST', 'change_requests', str(c['id']), 'decide', b={'status': 'Rejected'})
        self.assertEqual(r['before'], r['after'])
        self.assertEqual([x for x in self.api('GET', 'requirements') if x['id'] == c['req_id']][0]['status'], 'Rejected')

    def test08_input_validation(self):
        """TC08 Expected: invalid numbers/dates/enums/percent/duration are rejected with ValueError."""
        t = self.api('GET', 'tasks')[0]
        for bad in (dict(t, planned_cost=-5), dict(t, percent=150), dict(t, duration=0), dict(t, duration='abc'), dict(t, name=' '), dict(t, wbs_id=999)):
            with self.assertRaises(ValueError): self.api('PUT', 'tasks', str(t['id']), b=bad)
        with self.assertRaises(ValueError): self.api('PUT', 'charter', b=dict(self.api('GET', 'charter'), start_date='31-08-2026'))
        with self.assertRaises(ValueError): self.api('POST', 'defects', b=dict(title='x', severity='Huge', status='Open'))
        with self.assertRaises(ValueError): self.api('POST', 'risks', b=dict(description='x', likelihood=9, impact=1))

    def test09_circular_dependency_and_budget(self):
        """TC09 Expected: cyclic dependency and over-budget activity are rejected."""
        t = self.api('GET', 'tasks')[0]
        with self.assertRaisesRegex(ValueError, 'Circular'): self.api('PUT', 'tasks', str(t['id']), b=dict(t, depends_on='9'))
        with self.assertRaisesRegex(ValueError, 'itself'): self.api('PUT', 'tasks', str(t['id']), b=dict(t, depends_on='1'))
        with self.assertRaisesRegex(ValueError, 'exceed the approved budget'): self.api('POST', 'tasks', b=dict(name='Big', wbs_id=3, duration=5, planned_cost=900000))
        with self.assertRaisesRegex(ValueError, 'does not exist'): self.api('POST', 'tasks', b=dict(name='x', wbs_id=3, duration=5, planned_cost=1, depends_on='77'))

    def test10_referential_integrity(self):
        """TC10 Expected: cannot delete activity with dependents, requirement used in WBS, or team member with assignments."""
        with self.assertRaisesRegex(ValueError, 'depend'): self.api('DELETE', 'tasks', '2')
        with self.assertRaises(ValueError): self.api('DELETE', 'requirements', '1')
        with self.assertRaises(ValueError): self.api('DELETE', 'team', '2')
        with self.assertRaisesRegex(ValueError, 'only be approved|already used'): self.api('PUT', 'requirements', '1', b=dict(title='x', priority='High', status='Proposed'))

    def test11_closure_rules(self):
        """TC11 Expected: project cannot be closed with critical defects/pending CRs/no notes; can close when resolved."""
        ch = self.api('GET', 'charter')
        with self.assertRaisesRegex(ValueError, 'Closure notes'): self.api('PUT', 'charter', b=dict(ch, status='Closed'))
        with self.assertRaisesRegex(ValueError, 'critical defects'): self.api('PUT', 'charter', b=dict(ch, status='Closed', closure_notes='done'))
        for d in self.api('GET', 'defects'): self.api('PUT', 'defects', str(d['id']), b=dict(d, status='Closed'))
        with self.assertRaisesRegex(ValueError, 'pending change'): self.api('PUT', 'charter', b=dict(ch, status='Closed', closure_notes='done'))
        for c in self.api('GET', 'change_requests'): self.api('POST', 'change_requests', str(c['id']), 'decide', b={'status': 'Rejected'})
        self.api('PUT', 'charter', b=dict(ch, status='Closed', closure_notes='Delivered'))
        self.assertEqual(self.api('GET', 'charter')['status'], 'Closed')

    def test12_risk_ranking_and_defects(self):
        """TC12 Expected: risks sorted by likelihood x impact (top = 20); 2 unresolved critical defects reported."""
        r = self.api('GET', 'risks'); self.assertEqual(r[0]['score'], 20); self.assertEqual([x['score'] for x in r], sorted([x['score'] for x in r], reverse=True))
        self.assertEqual(len(self.api('GET', 'dashboard')['critical_defects']), 2)

    def test13_consistency_uncovered_requirement(self):
        """TC13 Expected: an approved requirement with no WBS item raises a warning."""
        self.api('POST', 'requirements', b=dict(title='Pharmacy integration', priority='Low', status='Approved'))
        self.assertIn('not covered by the WBS', ' '.join(w['msg'] for w in self.api('GET', 'analysis')['warnings']))

    def test14_delay_propagation_updates_deadline(self):
        """TC14 Expected: a 30-day delay on activity 8 moves finish past the 16-week deadline and raises a critical warning."""
        t = self.api('GET', 'tasks')[7]; self.api('PUT', 'tasks', '8', b=dict(t, delay_days=30))
        a = self.api('GET', 'analysis'); self.assertGreater(a['project']['days_past_deadline'], 0)
        self.assertTrue(any(w['level'] == 'critical' and 'deadline' in w['msg'] for w in a['warnings']))

if __name__ == '__main__': unittest.main(verbosity=2)
