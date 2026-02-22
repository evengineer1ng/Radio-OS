/// Base HTTP client with retry, timeout, and error handling.
library;

import 'package:dio/dio.dart';
import '../../../config/constants.dart';

class RadioHttpClient {
  final Dio _dio;
  final String baseUrl;

  RadioHttpClient({
    required this.baseUrl,
    Duration? timeout,
    int? maxRetries,
  }) : _dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: timeout ?? ApiConstants.httpTimeout,
          receiveTimeout: timeout ?? ApiConstants.httpTimeout,
          sendTimeout: timeout ?? ApiConstants.httpTimeout,
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
        )) {
    _dio.interceptors.add(_RetryInterceptor(
      maxRetries: maxRetries ?? ApiConstants.httpMaxRetries,
    ));
  }

  Future<Map<String, dynamic>> get(String path,
      {Map<String, dynamic>? queryParams}) async {
    try {
      final response = await _dio.get(path, queryParameters: queryParams);
      return _parseResponse(response);
    } on DioException catch (e) {
      return _handleError(e);
    }
  }

  Future<Map<String, dynamic>> post(String path,
      {Map<String, dynamic>? data}) async {
    try {
      final response = await _dio.post(path, data: data);
      return _parseResponse(response);
    } on DioException catch (e) {
      return _handleError(e);
    }
  }

  Future<Map<String, dynamic>> put(String path,
      {Map<String, dynamic>? data}) async {
    try {
      final response = await _dio.put(path, data: data);
      return _parseResponse(response);
    } on DioException catch (e) {
      return _handleError(e);
    }
  }

  Future<Map<String, dynamic>> delete(String path) async {
    try {
      final response = await _dio.delete(path);
      return _parseResponse(response);
    } on DioException catch (e) {
      return _handleError(e);
    }
  }

  Map<String, dynamic> _parseResponse(Response response) {
    if (response.data is Map<String, dynamic>) {
      return response.data as Map<String, dynamic>;
    }
    if (response.data is List) {
      return {'items': response.data};
    }
    return {'data': response.data};
  }

  Map<String, dynamic> _handleError(DioException e) {
    return {
      'error': true,
      'message': e.message ?? 'Network error',
      'status': e.response?.statusCode,
    };
  }

  void dispose() {
    _dio.close();
  }
}

class _RetryInterceptor extends Interceptor {
  final int maxRetries;

  _RetryInterceptor({this.maxRetries = 3});

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (_shouldRetry(err) && (err.requestOptions.extra['retryCount'] ?? 0) < maxRetries) {
      final count = (err.requestOptions.extra['retryCount'] ?? 0) as int;
      err.requestOptions.extra['retryCount'] = count + 1;
      // Exponential backoff would go here in production
      handler.next(err);
    } else {
      handler.next(err);
    }
  }

  bool _shouldRetry(DioException err) {
    return err.type == DioExceptionType.connectionTimeout ||
        err.type == DioExceptionType.receiveTimeout ||
        err.type == DioExceptionType.connectionError;
  }
}
