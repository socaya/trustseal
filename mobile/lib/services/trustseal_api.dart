import 'dart:convert';
import 'dart:io';

/// Response wrapper returned by [TrustSealApiClient].
class ApiResponse {
  final int statusCode;
  final Map<String, dynamic> body;

  const ApiResponse({required this.statusCode, required this.body});

  bool get isOk => statusCode >= 200 && statusCode < 300;
}

typedef ApiTransport = Future<ApiResponse> Function(
  String method,
  Uri uri,
  Map<String, String> headers,
  Map<String, dynamic>? jsonBody,
);

/// Authenticated REST API client wired to all TRUSTSEAL backend endpoints:
/// - Auth JWT (`/api/auth/login`, `/api/auth/refresh`, `/api/auth/me`)
/// - Documents & Stamps (`/api/tsd/`, `/api/tsd-stamps/`)
/// - Projects, Tasks, Timesheets & Expenses (`/api/projects/`, `/api/timesheets/`)
/// - Contracts & eIDAS 2.0 eSignature (`/api/esignatures/send`, `/api/eidas/standards`)
/// - Public Verification (`/api/esignatures/verify/<query>`)
class TrustSealApiClient {
  String baseUrl;
  String? accessToken;
  String? refreshToken;
  Map<String, dynamic>? currentUser;
  final ApiTransport? _transport;

  TrustSealApiClient({
    this.baseUrl = 'http://127.0.0.1:5017',
    ApiTransport? transport,
  }) : _transport = transport;

  bool get isAuthenticated => accessToken != null && accessToken!.isNotEmpty;

  Future<ApiResponse> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool auth = true,
  }) async {
    final cleanBase = baseUrl.replaceAll(RegExp(r'/+$'), '');
    final uri = Uri.parse('$cleanBase$path');
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-Requested-With': 'fetch',
    };
    if (auth && accessToken != null && accessToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $accessToken';
    }

    if (_transport != null) {
      return _transport!(method, uri, headers, body);
    }

    final client = HttpClient();
    client.connectionTimeout = const Duration(seconds: 12);
    try {
      final req = await client.openUrl(method, uri);
      headers.forEach((k, v) => req.headers.set(k, v));
      if (body != null) {
        req.write(jsonEncode(body));
      }
      final resp = await req.close();
      final text = await resp.transform(utf8.decoder).join();
      Map<String, dynamic> parsed = {};
      if (text.trim().isNotEmpty) {
        final decoded = jsonDecode(text);
        if (decoded is Map<String, dynamic>) {
          parsed = decoded;
        } else if (decoded is List) {
          parsed = {'items': decoded};
        }
      }
      return ApiResponse(statusCode: resp.statusCode, body: parsed);
    } finally {
      client.close(force: true);
    }
  }

  // ---- Authentication ----

  Future<ApiResponse> login(String identifier, String password) async {
    final res = await _request(
      'POST',
      '/api/auth/login',
      auth: false,
      body: {'identifier': identifier, 'password': password},
    );
    if (res.isOk) {
      accessToken = res.body['access_token'] as String?;
      refreshToken = res.body['refresh_token'] as String?;
      currentUser = (res.body['user'] as Map?)?.cast<String, dynamic>();
    }
    return res;
  }

  Future<void> logout() async {
    try {
      if (isAuthenticated) {
        await _request('POST', '/api/auth/logout');
      }
    } catch (_) {}
    accessToken = null;
    refreshToken = null;
    currentUser = null;
  }

  // ---- Module 1 & 4: Documents & Stamps ----

  Future<List<Map<String, dynamic>>> fetchDocuments() async {
    final res = await _request('GET', '/api/tsd/');
    if (!res.isOk) return [];
    final raw = (res.body['documents'] ?? res.body['items'] ?? []) as List;
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> fetchStamps() async {
    final res = await _request('GET', '/api/tsd-stamps/');
    if (!res.isOk) return [];
    final raw = (res.body['stamps'] ?? res.body['items'] ?? []) as List;
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  // ---- Module 2: Projects, Tasks, Timesheets & Expenses ----

  Future<List<Map<String, dynamic>>> fetchProjects() async {
    final res = await _request('GET', '/api/projects/');
    if (!res.isOk) return [];
    final raw = (res.body['projects'] ?? res.body['items'] ?? []) as List;
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> fetchTimesheets() async {
    final res = await _request('GET', '/api/timesheets/');
    if (!res.isOk) return [];
    final raw = (res.body['timesheets'] ?? res.body['entries'] ?? res.body['items'] ?? []) as List;
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<ApiResponse> logTimesheet({
    required int projectId,
    required double hours,
    required String workDate,
    required String description,
    bool billable = true,
  }) {
    return _request(
      'POST',
      '/api/timesheets/',
      body: {
        'project_id': projectId,
        'hours': hours,
        'work_date': workDate,
        'description': description,
        'billable': billable,
      },
    );
  }

  // ---- Module 3: Contracts & eIDAS 2.0 Send for eSignature ----

  Future<Map<String, dynamic>> fetchSignaturePackages() async {
    final res = await _request('GET', '/api/esignatures/send');
    if (!res.isOk) {
      return {'summary': {}, 'packages': <Map<String, dynamic>>[]};
    }
    return res.body;
  }

  Future<ApiResponse> sendForSignature({
    required String title,
    required String recipientName,
    required String recipientEmail,
    String eidasLevel = 'AES',
    String padesProfile = 'PAdES-B-LTA',
    String routingMode = 'sequential',
    int expiresInDays = 30,
  }) {
    return _request(
      'POST',
      '/api/esignatures/send',
      body: {
        'title': title,
        'routing_mode': routingMode,
        'eidas_level': eidasLevel,
        'pades_profile': padesProfile,
        'expires_in_days': expiresInDays,
        'recipients': [
          {
            'name': recipientName,
            'email': recipientEmail,
            'role': 'signer',
            'signing_order': 1,
            'eidas_level': eidasLevel,
          },
        ],
      },
    );
  }

  Future<ApiResponse> remindPackage(int packageId) {
    return _request('POST', '/api/esignatures/send/$packageId/remind');
  }

  Future<Map<String, dynamic>> fetchEidasStandards() async {
    final res = await _request('GET', '/api/eidas/standards', auth: false);
    return res.isOk ? res.body : {};
  }

  // ---- Module 5: Public Cryptographic Verification ----

  Future<ApiResponse> verifyReferenceOrHash(String query) {
    final encoded = Uri.encodeComponent(query.trim());
    return _request('GET', '/api/esignatures/verify/$encoded', auth: false);
  }
}
