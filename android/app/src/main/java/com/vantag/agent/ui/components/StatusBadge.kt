package com.vantag.agent.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantag.agent.ui.theme.ErrorColor
import com.vantag.agent.ui.theme.SuccessColor
import com.vantag.agent.ui.theme.WarningColor

@Composable
fun StatusBadge(
    isOnline: Boolean,
    modifier: Modifier = Modifier
) {
    val color = if (isOnline) SuccessColor else ErrorColor
    val label = if (isOnline) "Online" else "Offline"
    Row(
        modifier = modifier
            .background(color.copy(alpha = 0.15f), RoundedCornerShape(100))
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(
            modifier = Modifier
                .size(6.dp)
                .background(color, CircleShape)
        )
        Text(label, color = color, fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun EventBadge(eventType: String) {
    val (color, label) = when (eventType) {
        "sweep" -> Pair(ErrorColor, "Sweep")
        "dwell" -> Pair(WarningColor, "Dwell")
        "empty_shelf" -> Pair(Color(0xFF3B82F6), "Empty Shelf")
        "tamper" -> Pair(Color(0xFFEC4899), "Tamper")
        else -> Pair(Color.Gray, eventType)
    }
    Box(
        modifier = Modifier
            .background(color.copy(alpha = 0.2f), RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp)
    ) {
        Text(label, color = color, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}
