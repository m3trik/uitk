#include <QObject>
#include <QEvent>
#include <QWidget>
#include <QMouseEvent>
#include <QApplication>
#include <QCursor>
#include <QStackedWidget>
#include <QAbstractButton>
#include <QPushButton>
#include <QComboBox>
#include <QSlider>
#include <QScrollBar>
#include <QDebug>
#include <QSet>
#include <QList>
#include <QVariant>
#include <regex>

class EventFactoryFilter : public QObject {
    Q_OBJECT

public:
    EventFactoryFilter(QObject* parent = nullptr, QObject* forwardEventsTo = nullptr, const QString& eventNamePrefix = "")
        : QObject(parent), forwardEventsTo(forwardEventsTo ? forwardEventsTo : this), eventNamePrefix(eventNamePrefix) {}

protected:
    bool eventFilter(QObject* obj, QEvent* event) override {
        QString methodName = formatEventName(event->type(), eventNamePrefix);
        // Attempt to find a corresponding slot in the forwardEventsTo object
        if (forwardEventsTo->metaObject()->indexOfSlot(QMetaObject::normalizedSignature(qPrintable(methodName + "(QWidget*, QEvent*)"))) >= 0) {
            QMetaObject::invokeMethod(forwardEventsTo, qPrintable(methodName), Qt::DirectConnection, Q_ARG(QWidget*, qobject_cast<QWidget*>(obj)), Q_ARG(QEvent*, event));
            return true;
        }
        return false;
    }

private:
    QObject* forwardEventsTo;
    QString eventNamePrefix;

    QString formatEventName(QEvent::Type eventType, const QString& prefix = "") {
        static const std::regex regexPattern("^.*\\.([A-Z])([^B]*)(?:Button)?(.*)$");
        std::string eventTypeStr = QString::number(static_cast<int>(eventType)).toStdString();
        std::smatch matches;

        if (std::regex_match(eventTypeStr, matches, regexPattern)) {
            QString formattedName = prefix + QString(matches[1].str().c_str()).toLower() + QString(matches[2].str().c_str()) + QString(matches[3].str.c_str()) + "Event";
            return formattedName;
        }
        return prefix + "event";
    }
};

class MouseTracking : public QObject {
    Q_OBJECT

public:
    MouseTracking(QWidget* parent, const QString& logLevel = "WARNING")
        : QObject(parent), _prevMouseOver(), _mouseOver(), _filteredWidgets() {
        if (!parent->inherits("QWidget")) {
            qFatal("Parent must be a QWidget derived type");
        }
        parent->installEventFilter(this);
        // Initialize logging level (for simplicity, we'll use qDebug here)
        qDebug() << "MouseTracking initialized with log level:" << logLevel;
    }

protected:
    bool eventFilter(QObject* obj, QEvent* event) override {
        if (event->type() == QEvent::MouseMove) {
            qDebug() << "MouseMove event filter triggered by:" << obj << "with event:" << event->type();
            track();
        } else if (event->type() == QEvent::MouseButtonRelease) {
            QWidget* topWidget = QApplication::widgetAt(QCursor::pos());
            if (topWidget && qobject_cast<QAbstractButton*>(topWidget) && !qobject_cast<QAbstractButton*>(topWidget)->isDown()) {
                qDebug() << "Mouse button release event detected on:" << topWidget;
                sendReleaseEvent(topWidget, static_cast<QMouseEvent*>(event)->button());
            }
        }
        return QObject::eventFilter(obj, event);
    }

private:
    QList<QWidget*> _prevMouseOver;
    QList<QWidget*> _mouseOver;
    QSet<QWidget*> _filteredWidgets;

    bool shouldCaptureMouse(QWidget* widget) {
        struct WidgetCondition {
            const char* widgetType;
            std::function<bool(QWidget*)> condition;
        };

        std::vector<WidgetCondition> widgetConditions = {
            {"QPushButton", [](QWidget* w) { return !qobject_cast<QPushButton*>(w)->isDown(); }},
            {"QComboBox", [](QWidget* w) { return !qobject_cast<QComboBox*>(w)->view()->isVisible(); }},
            {"QSlider", [](QWidget* w) { return !qobject_cast<QSlider*>(w)->isSliderDown(); }},
            {"QScrollBar", [](QWidget* w) { return !qobject_cast<QScrollBar*>(w)->isSliderDown(); }},
        };

        for (const auto& condition : widgetConditions) {
            if (widget->inherits(condition.widgetType) && condition.condition(widget)) {
                qDebug() << "Not capturing mouse for" << widget->metaObject()->className() << "under specified condition";
                return false;
            }
        }
        return true;
    }

    void updateWidgetsUnderCursor() {
        getChildWidgets();
        QWidget* topWidget = QApplication::widgetAt(QCursor::pos());
        _mouseOver = topWidget && _widgets.contains(topWidget) ? QList<QWidget*>{topWidget} : QList<QWidget*>{};
        qDebug() << "Widgets under cursor:" << _mouseOver;
    }

    void getChildWidgets() {
        QWidget* parentWidget = qobject_cast<QWidget*>(parent());
        _widgets = parentWidget->findChildren<QWidget*>();
    }

    void track() {
        qDebug() << "Previous widgets under cursor:" << _prevMouseOver;
        qDebug() << "Current widgets under cursor:" << _mouseOver;

        releaseMouseForWidgets(_mouseOver);
        updateWidgetsUnderCursor();

        for (QWidget* widget : _prevMouseOver) {
            if (!_mouseOver.contains(widget)) {
                sendLeaveEvent(widget);
            }
        }
        for (QWidget* widget : _mouseOver) {
            if (!_prevMouseOver.contains(widget)) {
                sendEnterEvent(widget);
            }
        }

        handleMouseGrab();
        _prevMouseOver = _mouseOver;
        filterViewportWidgets();
    }

    void releaseMouseForWidgets(const QList<QWidget*>& widgets) {
        for (QWidget* widget : widgets) {
            widget->releaseMouse();
        }
    }

    void sendLeaveEvent(QWidget* widget) {
        qDebug() << "Sending Leave event to:" << widget << "Name:" << widget->objectName();
        QEvent leaveEvent(QEvent::Leave);
        QApplication::sendEvent(widget, &leaveEvent);
    }

    void sendEnterEvent(QWidget* widget) {
        qDebug() << "Sending Enter event to:" << widget << "Name:" << widget->objectName();
        QEvent enterEvent(QEvent::Enter);
        QApplication::sendEvent(widget, &enterEvent);
    }

    void sendReleaseEvent(QWidget* widget, Qt::MouseButton button) {
        qDebug() << "Sending Release event to:" << widget << "Name:" << widget->objectName();
        QMouseEvent releaseEvent(QEvent::MouseButtonRelease, QCursor::pos(), button, button, Qt::NoModifier);
        QApplication::postEvent(widget, new QMouseEvent(releaseEvent));
    }

    void handleMouseGrab() {
        QWidget* topWidget = QApplication::widgetAt(QCursor::pos());
        if (topWidget) {
            qDebug() << "Top widget under cursor:" << topWidget;
            QWidget* widgetToGrab = shouldCaptureMouse(topWidget) ? topWidget : QApplication::activeWindow();
            qDebug() << "Grabbing mouse for widget:" << widgetToGrab;
            widgetToGrab->grabMouse();
        } else {
            qDebug() << "No widget under cursor. Grabbing mouse for active window.";
            QApplication::activeWindow()->grabMouse();
        }
    }

    void filterViewportWidgets() {
        for (QWidget* widget : _widgets) {
            if (widget->inherits("QAbstractScrollArea") && !_filteredWidgets.contains(widget)) {
                _filteredWidgets.insert(widget);
                handleViewportWidget(qobject_cast<QAbstractScrollArea*>(widget));
            }
        }
    }

    void handleViewportWidget(QAbstractScrollArea* widget) {
        if (!widget) return;
        auto originalMouseMoveEvent = widget->mouseMoveEvent;
        widget->mouseMoveEvent = [originalMouseMoveEvent](QMouseEvent* event) mutable {
            originalMouseMoveEvent(event);
            event->ignore();
        };
    }

    QList<QWidget*> _widgets;
};

#include "events.moc"
