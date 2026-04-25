import 'package:flutter/material.dart';
import '../services/cart_service.dart';

class CartScreen extends StatelessWidget {
  const CartScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Cart')),
      body: AnimatedBuilder(
        animation: CartService.instance,
        builder: (_, __) {
          final items = CartService.instance.items;
          if (items.isEmpty) {
            return const Center(child: Text('Your cart is empty'));
          }
          return Column(
            children: [
              Expanded(
                child: ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (_, i) {
                    final item = items[i];
                    return ListTile(
                      title: Text(item.product.name),
                      subtitle: Text('Qty: ${item.quantity}  ·  ₹${item.subtotal.toStringAsFixed(0)}'),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete),
                        onPressed: () => CartService.instance.remove(item.product.id),
                      ),
                    );
                  },
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Total: ₹${CartService.instance.total.toStringAsFixed(0)}',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                    ElevatedButton(
                      onPressed: () {
                        CartService.instance.clear();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Order placed')),
                        );
                      },
                      child: const Text('Checkout'),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
