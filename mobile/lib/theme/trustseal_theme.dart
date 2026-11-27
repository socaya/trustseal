import 'package:flutter/material.dart';

/// TRUSTSEAL Executive Brand Theme — Deep Navy, Verified Emerald, calm slate surfaces,
/// hairline dividers, crisp 7px status dots, and zero filled pastel chips.
class TrustSealTheme {
  static const Color navyDark = Color(0xFF001A4D);
  static const Color navy = Color(0xFF002769);
  static const Color navyAccent = Color(0xFF013688);
  static const Color emerald = Color(0xFF02982E);
  static const Color emeraldDark = Color(0xFF027F26);
  static const Color surfaceTint = Color(0xFFF4F7FC);
  static const Color railTint = Color(0xFFF8FAFD);
  static const Color border = Color(0xFFDBE4F2);
  static const Color ink = Color(0xFF0F172A);
  static const Color muted = Color(0xFF475569);
  static const Color subtle = Color(0xFF64748B);
  static const Color danger = Color(0xFFDC2626);
  static const Color warning = Color(0xFFD97706);

  static ThemeData build() {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: Colors.white,
      colorScheme: ColorScheme.fromSeed(
        seedColor: navy,
        primary: navy,
        secondary: emerald,
        surface: Colors.white,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: navy,
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: Colors.white,
          letterSpacing: -0.2,
        ),
      ),
      dividerColor: border,
      textTheme: const TextTheme(
        headlineSmall: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: ink),
        titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: navy),
        bodyMedium: TextStyle(fontSize: 14, color: ink, height: 1.45),
        bodySmall: TextStyle(fontSize: 13, color: muted, height: 1.4),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(7),
          borderSide: const BorderSide(color: Color(0xFFCBD5E1)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(7),
          borderSide: const BorderSide(color: Color(0xFFCBD5E1)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(7),
          borderSide: const BorderSide(color: navy, width: 1.6),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: navy,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(7)),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          elevation: 0,
        ),
      ),
    );
  }
}

/// Crisp typographic status indicator with a 7px semantic dot (no filled AI chips).
class StatusDotLabel extends StatelessWidget {
  final String label;
  final Color dotColor;

  const StatusDotLabel({
    super.key,
    required this.label,
    required this.dotColor,
  });

  factory StatusDotLabel.forStatus(String status) {
    final s = status.toLowerCase();
    if (s == 'completed' || s == 'signed' || s == 'approved' || s == 'verified' || s == 'active') {
      return StatusDotLabel(label: _titleCase(status), dotColor: TrustSealTheme.emerald);
    }
    if (s == 'sent' || s == 'in_progress' || s == 'executing' || s == 'qes') {
      return StatusDotLabel(label: _titleCase(status), dotColor: TrustSealTheme.navy);
    }
    if (s == 'declined' || s == 'voided' || s == 'expired' || s == 'failed') {
      return StatusDotLabel(label: _titleCase(status), dotColor: TrustSealTheme.danger);
    }
    return StatusDotLabel(label: _titleCase(status), dotColor: TrustSealTheme.subtle);
  }

  static String _titleCase(String raw) {
    return raw.replaceAll('_', ' ').split(' ').map((w) {
      if (w.isEmpty) return w;
      return w[0].toUpperCase() + w.substring(1).toLowerCase();
    }).join(' ');
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: const TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: TrustSealTheme.ink,
          ),
        ),
      ],
    );
  }
}
