
class ReliefRequest {
  final String id;
  final String needType;
  final String urgency;
  final String location;
  final String description;
  final String status;
  final String createdAt;

  const ReliefRequest({
    required this.id,
    required this.needType,
    required this.urgency,
    required this.location,
    required this.description,
    required this.status,
    required this.createdAt,
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'needType': needType,
      'urgency': urgency,
      'location': location,
      'description': description,
      'status': status,
      'createdAt': createdAt,
    };
  }

  factory ReliefRequest.fromJson(Map<String, dynamic> json) {
    return ReliefRequest(
      id: json['id'] as String,
      needType: json['needType'] as String,
      urgency: json['urgency'] as String,
      location: json['location'] as String,
      description: json['description'] as String,
      status: json['status'] as String,
      createdAt: json['createdAt'] as String,
    );
  }
}
