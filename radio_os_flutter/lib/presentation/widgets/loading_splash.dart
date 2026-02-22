/// Loading splash — shown while waiting for backend connection.
library;

import 'package:flutter/material.dart';

class LoadingSplash extends StatelessWidget {
  final String message;

  const LoadingSplash({
    super.key,
    this.message = 'Connecting to Radio OS...',
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0e0e0e),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Logo placeholder
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                    color: const Color(0xFF4cc9f0).withValues(alpha: 0.3),
                    width: 2),
              ),
              child: const Icon(
                Icons.radio,
                size: 40,
                color: Color(0xFF4cc9f0),
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'RADIO OS',
              style: TextStyle(
                color: Color(0xFFe8e8e8),
                fontSize: 24,
                fontWeight: FontWeight.w800,
                letterSpacing: 4,
              ),
            ),
            const SizedBox(height: 16),
            const SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Color(0xFF4cc9f0),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              message,
              style: const TextStyle(
                color: Color(0xFF9a9a9a),
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
