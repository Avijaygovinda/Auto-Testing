import 'package:flutter/foundation.dart';
import '../models/product.dart';
import '../models/cart_item.dart';

/// Singleton cart held in memory. Cart is NOT persisted across app restarts.
class CartService extends ChangeNotifier {
  static final CartService instance = CartService._();
  CartService._();

  final List<CartItem> _items = [];

  List<CartItem> get items => List.unmodifiable(_items);

  int get itemCount => _items.fold(0, (sum, i) => sum + i.quantity);

  double get total => _items.fold(0.0, (sum, i) => sum + i.subtotal);

  void add(Product product) {
    final existing = _items.indexWhere((i) => i.product.id == product.id);
    if (existing >= 0) {
      _items[existing].quantity += 1;
    } else {
      _items.add(CartItem(product: product));
    }
    notifyListeners();
  }

  void remove(String productId) {
    _items.removeWhere((i) => i.product.id == productId);
    notifyListeners();
  }

  void clear() {
    _items.clear();
    notifyListeners();
  }
}
