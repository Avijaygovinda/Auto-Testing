import '../models/product.dart';

/// Fake API service. In real app this would hit HTTP endpoints.
/// Simulates 1-second network delay so loading states can be tested.
class ApiService {
  static final List<Product> _fakeProducts = [
    Product(
      id: 'p1',
      name: 'Wireless Headphones',
      description: 'Noise-cancelling over-ear headphones with 30hr battery.',
      price: 2999.0,
      imageUrl: 'https://example.com/p1.jpg',
      stock: 12,
    ),
    Product(
      id: 'p2',
      name: 'Smart Watch',
      description: 'Fitness tracker with heart-rate monitor.',
      price: 4499.0,
      imageUrl: 'https://example.com/p2.jpg',
      stock: 0,
    ),
    Product(
      id: 'p3',
      name: 'Bluetooth Speaker',
      description: 'Portable waterproof speaker, 12hr playback.',
      price: 1799.0,
      imageUrl: 'https://example.com/p3.jpg',
      stock: 5,
    ),
  ];

  Future<List<Product>> fetchProducts() async {
    await Future.delayed(const Duration(seconds: 1));
    return _fakeProducts;
  }

  Future<Product?> fetchProductById(String id) async {
    await Future.delayed(const Duration(milliseconds: 500));
    try {
      return _fakeProducts.firstWhere((p) => p.id == id);
    } catch (_) {
      return null;
    }
  }
}
