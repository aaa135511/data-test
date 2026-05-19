//+------------------------------------------------------------------+
//|                                         DoubleDragon_Live_V6.mq5 |
//|                                  核心：突破200/OCO/3min/极速追踪/盈利加仓|
//|                       实盘增强版：适配3位/2位精度、自动填充模式        |
//+------------------------------------------------------------------+
#property copyright "Expert"
#property link      "https://m.jrjr.com/"
#property version   "6.00"
#property strict

#include <Trade\Trade.mqh>

//--- 基础参数
input double LotSize         = 0.1;       // 基础首单手数
input double AddLotSize      = 0.1;       // 盈利加仓手数
input int    Slippage        = 10;        // 滑点 (10点 = 0.1美元)
input int    MagicNumber     = 888888;    // EA识别码
input double DailyMaxLoss    = 300.0;     // 核心任务4：日亏损关机 (美元)

//--- 交易价格区间
input double PriceMin        = 4000.0;    // 交易区间底价
input double PriceMax        = 6000.0;    // 交易区间顶价

//--- 进场参数
input int    DistancePoints  = 200;       // 核心任务1：挂单距离

//--- 追踪与止损参数
input int    InitialStopLoss = 10;        // 初始止损 (10点)
input int    TrailingStart   = 5;         // 获利 5 点激活追踪并加仓
input int    TrailingStop    = 2;         // 追踪回撤距离 (2点)
input int    TimeLimitMin    = 3;         // 核心任务3：持仓时间限制 (分钟)

//--- 全局变量
CTrade trade;
datetime DayStartTime;
double   InitialBalance;
bool     IsScaledIn = false;
int      SymbolDigits;      // 存储品种小数点位数

//+------------------------------------------------------------------+
//| 初始化                                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    // 获取品种精度 (实盘关键：2位还是3位)
    SymbolDigits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(Slippage);

    // 实盘关键：自动设置填充模式 (FOK/IOC)
    // 很多实盘报错是因为模拟盘默认是Return，实盘需要FOK
    trade.SetTypeFillingBySymbol(_Symbol);

    DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
    InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

    Print("--- EA 实盘增强版 V6 已启动 ---");
    Print("当前品种精度: ", SymbolDigits, " 位小数");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 主循环                                                            |
//+------------------------------------------------------------------+
void OnTick()
{
    if(!CheckDailyLoss()) return;

    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(bid < PriceMin || bid > PriceMax) return;

    HandlePositionsLogic();
    ManageOrders();
}

//+------------------------------------------------------------------+
//| 核心任务4：日损检查                                                |
//+------------------------------------------------------------------+
bool CheckDailyLoss()
{
    if(iTime(_Symbol, PERIOD_D1, 0) != DayStartTime)
    {
        DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
        InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    }
    double currentLoss = InitialBalance - AccountInfoDouble(ACCOUNT_EQUITY);
    if(currentLoss >= DailyMaxLoss)
    {
        Print("🛑 触发日损限制！执行关机。");
        CloseAllPositions();
        CancelAllOrders();
        ExpertRemove();
        return false;
    }
    return true;
}

//+------------------------------------------------------------------+
//| 持仓综合管理 (含加仓、时间止损、极速追踪)                            |
//+------------------------------------------------------------------+
void HandlePositionsLogic()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double point = _Point;
    int positionsCount = 0;

    for(int i=PositionsTotal()-1; i>=0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                positionsCount++;
                long posType = PositionGetInteger(POSITION_TYPE);
                double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                double currentSL = PositionGetDouble(POSITION_SL);

                // 3分钟强制平仓
                long openTime = PositionGetInteger(POSITION_TIME);
                if(TimeCurrent() - openTime >= TimeLimitMin * 60)
                {
                    trade.PositionClose(ticket);
                    continue;
                }

                // 极速追踪与加仓
                if(posType == POSITION_TYPE_BUY)
                {
                    double profitPoints = (bid - openPrice) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        // 满足加仓条件
                        if(positionsCount == 1 && !IsScaledIn)
                        {
                            double slPrice = NormalizeDouble(bid - InitialStopLoss * point, SymbolDigits);
                            if(trade.Buy(AddLotSize, _Symbol, ask, slPrice, 0, "Scale-In"))
                            {
                                IsScaledIn = true;
                                Print("💰 盈利加仓成功 (实盘检测)");
                            }
                        }
                        // 移动止损 (归一化价格)
                        double newSL = NormalizeDouble(bid - TrailingStop * point, SymbolDigits);
                        if(newSL > currentSL + point || currentSL == 0)
                            trade.PositionModify(ticket, newSL, 0);
                    }
                }
                else if(posType == POSITION_TYPE_SELL)
                {
                    double profitPoints = (openPrice - ask) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        if(positionsCount == 1 && !IsScaledIn)
                        {
                            double slPrice = NormalizeDouble(ask + InitialStopLoss * point, SymbolDigits);
                            if(trade.Sell(AddLotSize, _Symbol, bid, slPrice, 0, "Scale-In"))
                            {
                                IsScaledIn = true;
                                Print("💰 盈利加仓成功 (实盘检测)");
                            }
                        }
                        double newSL = NormalizeDouble(ask + TrailingStop * point, SymbolDigits);
                        if(newSL < currentSL - point || currentSL == 0)
                            trade.PositionModify(ticket, newSL, 0);
                    }
                }
            }
        }
    }
    if(positionsCount == 0) IsScaledIn = false;
}

//+------------------------------------------------------------------+
//| 核心任务1 & 2：OCO 挂单管理                                       |
//+------------------------------------------------------------------+
void ManageOrders()
{
    int ordersCount = 0;
    int positionsCount = 0;

    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) positionsCount++;

    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) ordersCount++;

    if(positionsCount > 0)
    {
        if(ordersCount > 0) CancelAllOrders();
        return;
    }

    if(positionsCount == 0 && ordersCount == 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double point = _Point;

        // 关键：对所有价格进行 NormalizeDouble 归一化处理
        double buyStopPrice = NormalizeDouble(ask + DistancePoints * point, SymbolDigits);
        double buySL = NormalizeDouble(buyStopPrice - InitialStopLoss * point, SymbolDigits);

        double sellStopPrice = NormalizeDouble(bid - DistancePoints * point, SymbolDigits);
        double sellSL = NormalizeDouble(sellStopPrice + InitialStopLoss * point, SymbolDigits);

        // 发送订单
        if(!trade.BuyStop(LotSize, buyStopPrice, _Symbol, buySL, 0, ORDER_TIME_GTC, 0, "Start"))
        {
            Print("❌ 买入挂单失败，错误码: ", GetLastError());
        }

        if(!trade.SellStop(LotSize, sellStopPrice, _Symbol, sellSL, 0, ORDER_TIME_GTC, 0, "Start"))
        {
            Print("❌ 卖出挂单失败，错误码: ", GetLastError());
        }
    }
}

//--- 工具函数
void CloseAllPositions()
{
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) trade.PositionClose(PositionGetTicket(i));
}

void CancelAllOrders()
{
    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)))
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) trade.OrderDelete(OrderGetTicket(i));
}