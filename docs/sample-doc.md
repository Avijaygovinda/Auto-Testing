# Sample Ecommerce App — Documentation

## Overview
A simple Flutter ecommerce mobile app for buying and selling products.

## User Flows

### Authentication
- Users must sign up before they can log in
- Login requires valid email + password
- Password must be at least 8 characters with one uppercase letter and one number
- After 3 failed login attempts, account is locked for 15 minutes
- "Forgot password" should send a reset link via email
- Successful login redirects to home screen

### Validation Rules
- Email must be in valid format (contains @ and domain)
- Empty fields should show inline error messages
- Loading state should disable the login button to prevent double-submit
- Error messages should be cleared when user starts typing again

### Visual Requirements
- App should work on screen widths from 320px (small phones) to 1024px (tablets)
- Login button must be visible without scrolling on all device sizes
- Error messages should be in red text and clearly visible
- All form fields must support proper keyboard types (email keyboard for email field, etc.)

## Screens

### Login Screen
- Email + password login.
- On success, navigate to Home Screen.

### Home Screen
- Shows a list of all products fetched from the API.
- Each item shows name, price (in ₹), and stock status.
- Tapping a product opens the Product Detail Screen.
- App bar shows a cart icon with a badge displaying total item count.
- Out-of-stock products are clearly marked.

### Product Detail Screen
- Shows full product info: name, price, description.
- "Add to Cart" button. Disabled when stock is 0.
- Tapping "Add to Cart" shows a confirmation snackbar and increments cart badge.

### Cart Screen
- Lists all items in the cart with name, quantity, subtotal.
- Each item has a delete button to remove it.
- Shows running total at the bottom.
- Checkout button clears the cart and shows "Order placed" snackbar.
- Empty state shows "Your cart is empty".

## Cart Behavior Rules
- Cart is in-memory only — does NOT persist across app restarts.
- Adding the same product twice increments its quantity, does not duplicate the row.
- Cart should be cleared on logout (TBD — verify with developer).

## Navigation Flow
Login → Home → Product Detail → (Add to Cart) → Home → Cart → Checkout → back to Home.
