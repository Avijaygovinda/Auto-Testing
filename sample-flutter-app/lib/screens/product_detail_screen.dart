import 'package:flutter/material.dart';
import '../models/product.dart';
import '../services/api_service.dart';
import '../services/cart_service.dart';

class ProductDetailScreen extends StatefulWidget {
  final String productId;
  const ProductDetailScreen({super.key, required this.productId});

  @override
  State<ProductDetailScreen> createState() => _ProductDetailScreenState();
}

class _ProductDetailScreenState extends State<ProductDetailScreen> {
  final ApiService _api = ApiService();
  Product? _product;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final p = await _api.fetchProductById(widget.productId);
    setState(() {
      _product = p;
      _loading = false;
    });
  }

  void _addToCart() {
    if (_product == null) return;
    CartService.instance.add(_product!);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Added to cart')),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_product == null) {
      return Scaffold(
        appBar: AppBar(),
        body: const Center(child: Text('Product not found')),
      );
    }
    final p = _product!;
    return Scaffold(
      appBar: AppBar(title: Text(p.name)),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(p.name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text('₹${p.price.toStringAsFixed(0)}', style: const TextStyle(fontSize: 18)),
            const SizedBox(height: 16),
            Text(p.description),
            const Spacer(),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: p.inStock ? _addToCart : null,
                child: Text(p.inStock ? 'Add to Cart' : 'Out of Stock'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
