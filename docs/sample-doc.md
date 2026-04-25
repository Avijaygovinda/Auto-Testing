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
1. **Login Screen** — email + password login
2. **Signup Screen** — create new account
3. **Home Screen** — product list
4. **Product Detail Screen**
5. **Cart Screen**
6. **Checkout Screen**
