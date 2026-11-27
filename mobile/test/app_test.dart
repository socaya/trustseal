import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:trustseal_mobile/main.dart';
import 'package:trustseal_mobile/services/trustseal_api.dart';

TrustSealApiClient _buildMockApi() {
  return TrustSealApiClient(
    baseUrl: 'http://127.0.0.1:5017',
    transport: (method, uri, headers, body) async {
      final path = uri.path;
      if (method == 'POST' && path == '/api/auth/login') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'access_token': 'mock-jwt-access',
            'refresh_token': 'mock-jwt-refresh',
            'user': {'id': 1, 'first_name': 'Demo', 'email': 'admin@trustseal.local'},
          },
        );
      }
      if (method == 'GET' && path == '/api/tsd/') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'documents': [
              {'id': 29, 'title': 'Master Services Agreement (MSA)', 'version': 3, 'status': 'draft'},
            ],
          },
        );
      }
      if (method == 'GET' && path == '/api/tsd-stamps/') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'stamps': [
              {'id': 1, 'name': 'Corporate Approval Seal', 'category': 'Official', 'status': 'active'},
            ],
          },
        );
      }
      if (method == 'GET' && path == '/api/projects/') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'projects': [
              {'id': 1, 'code': 'PRJ-2026-001', 'name': 'General Operations', 'status': 'executing', 'progress_pct': 65},
            ],
          },
        );
      }
      if (method == 'GET' && path == '/api/timesheets/') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'timesheets': [
              {'id': 1, 'description': 'eIDAS 2.0 integration review', 'work_date': '2026-11-27', 'hours': 4.0, 'status': 'approved'},
            ],
          },
        );
      }
      if (method == 'GET' && path == '/api/esignatures/send') {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'summary': {'total': 2, 'awaiting': 1, 'completed': 1, 'qes_count': 1, 'bulk_batches': 0},
            'packages': [
              {
                'id': 10,
                'package_ref': 'ESIG-2026-01QES001',
                'title': 'EU Cross-Border Vendor Agreement',
                'eidas_level': 'QES',
                'pades_profile': 'PAdES-B-LTA',
                'status': 'sent',
                'signed_count': 0,
                'signer_count': 1,
              },
            ],
          },
        );
      }
      if (method == 'POST' && path == '/api/esignatures/send') {
        return ApiResponse(
          statusCode: 201,
          body: {
            'package': {
              'id': 11,
              'package_ref': 'ESIG-2026-01NEW002',
              'title': body?['title'] ?? 'New Contract',
              'eidas_level': body?['eidas_level'] ?? 'QES',
              'pades_profile': body?['pades_profile'] ?? 'PAdES-B-LTA',
              'status': 'sent',
            },
          },
        );
      }
      if (method == 'GET' && path.startsWith('/api/esignatures/verify/')) {
        return const ApiResponse(
          statusCode: 200,
          body: {
            'verified': true,
            'certificate': {
              'package_ref': 'ESIG-2026-01QES001',
              'title': 'EU Cross-Border Vendor Agreement',
              'eidas_standard': {'name': 'Qualified Electronic Signature', 'code': 'QES'},
              'pades_conformance': {'profile': 'PAdES-B-LTA', 'ocsp_status': 'good'},
              'audit_chain': {'intact': true, 'event_count': 5},
            },
          },
        );
      }
      return const ApiResponse(statusCode: 200, body: {});
    },
  );
}

void main() {
  testWidgets('Full 5-module TRUSTSEAL Mobile flow: Login -> Home -> Projects -> Sign -> Docs -> Verify', (tester) async {
    final api = _buildMockApi();
    await tester.pumpWidget(TrustSealMobileApp(api: api));
    await tester.pumpAndSettle();

    // 1. Login screen
    expect(find.text('TRUSTSEAL MOBILE'), findsOneWidget);
    await tester.tap(find.byKey(const Key('login-submit-btn')));
    await tester.pumpAndSettle();

    // 2. Module 1: Home KPIs & recent eSignature package
    expect(find.text('Welcome back, Demo'), findsOneWidget);
    expect(find.text('EU Cross-Border Vendor Agreement'), findsOneWidget);

    Finder navTab(String label) => find.descendant(
          of: find.byType(BottomNavigationBar),
          matching: find.text(label),
        );

    // 3. Module 2: Projects & My Timesheets
    await tester.tap(navTab('Projects'));
    await tester.pumpAndSettle();
    expect(find.text('General Operations'), findsOneWidget);

    // 4. Module 3: Contracts & Sign (eIDAS 2.0)
    await tester.tap(navTab('Sign'));
    await tester.pumpAndSettle();
    expect(find.text('ESIG-2026-01QES001'), findsOneWidget);

    // 5. Module 4: Documents & Stamps
    await tester.tap(navTab('Docs'));
    await tester.pumpAndSettle();
    expect(find.text('Master Services Agreement (MSA)'), findsOneWidget);

    // 6. Module 5: Cryptographic Verification
    await tester.tap(navTab('Verify'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('verify-query-input')), 'ESIG-2026-01QES001');
    await tester.tap(find.byKey(const Key('verify-submit-btn')));
    await tester.pumpAndSettle();
    expect(find.text('Verified · Audit Chain Intact'), findsOneWidget);
    expect(find.text('Qualified Electronic Signature'), findsOneWidget);
  });
}
