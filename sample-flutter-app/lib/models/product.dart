class Product {
  final String id;
  final String name;
  final String description;
  final double price;
  final String imageUrl;
  final int stock;

  Product({
    required this.id,
    required this.name,
    required this.description,
    required this.price,
    required this.imageUrl,
    required this.stock,
  });

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String,
      price: (json['price'] as num).toDouble(),
      imageUrl: json['image_url'] as String,
      stock: json['stock'] as int,
    );
  }

  bool get inStock => stock > 0;
}
